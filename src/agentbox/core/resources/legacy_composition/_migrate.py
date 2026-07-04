from __future__ import annotations

from agentbox.core.data.payload_types import PromptBindingSpec

import hashlib
import json
import logging
from pathlib import Path

from agentbox.core.data.rows import AgentVersionFileRow
from agentbox.core.db import (
    AgentPromptResourceBindingManager,
    AgentVersionFileManager,
    AgentVersionManager,
    ResourceManager,
    ResourceVersionManager,
)
from agentbox.core.resources.legacy_composition._helpers import (
    backfill_slot_active_flag,
    binding_to_input,
    read_disk_file,
    slug_for,
)
from agentbox.core.resources.legacy_composition._report import (
    MIGRATION_ACTOR,
    MIGRATION_REASON,
    USER_TEMPLATE_MARKER,
    USER_TEMPLATE_MODE,
    CompositionMigrationReport,
)
from agentbox.core.resources.legacy_composition._store import get_or_create_resource

logger = logging.getLogger(__name__)


def _migrate_one_agent(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    prompt_bindings: AgentPromptResourceBindingManager,
    agent_version_files: AgentVersionFileManager,
    agent_id: str,
    composition: dict,
    version_id: int,
    bundle_dir: Path | None,
    report: CompositionMigrationReport,
) -> bool:
    """Migrate one agent. Returns True if any bindings were added."""
    files = agent_version_files.list_for_version(version_id)
    files_by_kind_path: dict[tuple[str, str], AgentVersionFileRow] = {}
    for f in files:
        files_by_kind_path[(f["kind"], f["relative_path"])] = f

    existing_bindings = prompt_bindings.list_for_agent(agent_id)
    existing_slots = {b["slot"] for b in existing_bindings if b.get("slot")}
    existing_marker_pairs = {
        (b["resource_id"], b["marker"])
        for b in existing_bindings
        if b.get("marker") and not b.get("slot")
    }

    new_inputs: list[PromptBindingSpec] = [binding_to_input(b) for b in existing_bindings]
    next_order = (
        max((b.get("display_order", 0) for b in existing_bindings), default=-1) + 1
    )
    added = 0

    def _maybe_add_slot(slot: str, kind: str, type_: str) -> None:
        nonlocal next_order, added
        if slot == "system":
            rel = composition.get("system") or composition.get("system_prompt")
        else:
            rel = composition.get(slot)
        if slot in existing_slots:
            return
        if not rel and slot != "system":
            return
        f = files_by_kind_path.get((kind, rel)) if rel is not None else None
        if f is None and slot == "system":
            for (k, _p), row in files_by_kind_path.items():
                if k == "system":
                    f = row
                    break
        content_text: str | None
        if f is not None:
            content_text = f["content"] or ""
            content_rel = rel or f["relative_path"]
        else:
            disk_rel = rel or ("prompts/system.md" if slot == "system" else None)
            content_text = read_disk_file(bundle_dir, disk_rel)
            content_rel = disk_rel or ""
            if content_text is None:
                logger.warning(
                    "composition migration: agent %s declares %s=%r but neither "
                    "agent_version_files (kind=%r, version %s) nor disk has it",
                    agent_id,
                    slot,
                    rel,
                    kind,
                    version_id,
                )
                return
        resource_id = get_or_create_resource(
            resources,
            resource_versions,
            content_text=content_text,
            type_=type_,
            relative_path=content_rel,
            agent_id=agent_id,
            report=report,
        )
        new_inputs.append(
            {
                "resource_id": resource_id,
                "marker": None,
                "mode": None,
                "slot": slot,
                "attach_as_reference": True,
                "pinned_version_id": None,
                "required": False,
                "display_order": next_order,
            }
        )
        next_order += 1
        added += 1

    _maybe_add_slot("system", "system", "document")
    _maybe_add_slot("input_schema", "input_schema", "schema")
    _maybe_add_slot("output_schema", "output_schema", "schema")

    user_template_rel = composition.get("user_template")
    if user_template_rel:
        f = files_by_kind_path.get(("user_template", user_template_rel))
        if f is not None:
            content_text = f["content"] or ""
        else:
            disk_text = read_disk_file(bundle_dir, user_template_rel)
            if disk_text is None:
                logger.warning(
                    "composition migration: agent %s declares user_template=%r but "
                    "neither agent_version_files (version %s) nor disk has it",
                    agent_id,
                    user_template_rel,
                    version_id,
                )
                content_text = None
            else:
                content_text = disk_text
        if content_text is not None:
            sha12 = hashlib.sha256(content_text.encode("utf-8")).hexdigest()[:12]
            candidate_slug = slug_for("document", sha12)
            existing = resources.get_by_slug(candidate_slug)
            candidate_resource_id = existing["id"] if existing else None
            already_bound = (
                candidate_resource_id is not None
                and (
                    candidate_resource_id,
                    USER_TEMPLATE_MARKER,
                )
                in existing_marker_pairs
            )

            if not already_bound:
                resource_id = get_or_create_resource(
                    resources,
                    resource_versions,
                    content_text=content_text,
                    type_="document",
                    relative_path=user_template_rel,
                    agent_id=agent_id,
                    report=report,
                )
                new_inputs.append(
                    {
                        "resource_id": resource_id,
                        "marker": USER_TEMPLATE_MARKER,
                        "mode": USER_TEMPLATE_MODE,
                        "slot": None,
                        "attach_as_reference": False,
                        "pinned_version_id": None,
                        "required": False,
                        "display_order": next_order,
                    }
                )
                next_order += 1
                added += 1

    if added == 0:
        return False

    prompt_bindings.replace_for_agent(
        agent_id,
        new_inputs,
        reason=MIGRATION_REASON,
        actor=MIGRATION_ACTOR,
    )
    report.bindings_created += added
    return True


def migrate_composition_to_bindings(
    resources: ResourceManager,
    resource_versions: ResourceVersionManager,
    prompt_bindings: AgentPromptResourceBindingManager,
    agent_version_files: AgentVersionFileManager,
    agent_versions: AgentVersionManager,
    *,
    only_agent_id: str | None = None,
    project_root: Path | None = None,
) -> CompositionMigrationReport:
    """Walk every agent's active version and migrate composition slots to bindings."""
    report = CompositionMigrationReport()
    backfill_slot_active_flag(prompt_bindings)
    agent_rows = agent_versions.list_latest_per_agent()

    for row in agent_rows:
        agent_id = row["agent_id"]
        if only_agent_id is not None and agent_id != only_agent_id:
            continue

        try:
            active = agent_versions.get_active(agent_id) or row
            config_json_str = active.get("config_json")
            if not config_json_str:
                report.agents_skipped_no_composition.append(agent_id)
                continue
            try:
                config = json.loads(config_json_str)
            except json.JSONDecodeError as exc:
                report.failed.append((agent_id, f"invalid config_json: {exc}"))
                continue
            composition = config.get("composition") or {}

            bundle_dir: Path | None = None
            if project_root is not None:
                src_path = active.get("source_path")
                if src_path:
                    candidate = (project_root / src_path).parent
                    if candidate.is_dir():
                        bundle_dir = candidate
            added = _migrate_one_agent(
                resources,
                resource_versions,
                prompt_bindings,
                agent_version_files,
                agent_id,
                composition,
                version_id=active["id"],
                bundle_dir=bundle_dir,
                report=report,
            )
            if added:
                report.agents_migrated.append(agent_id)
            else:
                report.agents_skipped_fully_bound.append(agent_id)
        except Exception as exc:
            logger.exception("composition migration: agent %s failed", agent_id)
            report.failed.append((agent_id, str(exc)))

    return report
