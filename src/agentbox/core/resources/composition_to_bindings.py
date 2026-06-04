"""One-shot sweep: composition slots → agent_prompt_resource_bindings.

For each agent's active version, reads
``config_json.composition`` and the snapshotted ``agent_version_files``
rows, and turns each composition slot into a resource + binding:

* ``composition.system``        → ``document`` resource + binding(slot="system", attach=1)
* ``composition.input_schema``  → ``schema`` resource + binding(slot="input_schema", attach=1)
* ``composition.output_schema`` → ``schema`` resource + binding(slot="output_schema", attach=1)
* ``composition.user_template`` → ``document`` resource + binding(marker="user_template", mode="inline")

Content-hash dedup: identical files across agents collapse to a single
``migrated:<type>:<sha12>`` repo resource. Each agent that reuses a
resource adds an ``agent:<agent_id>`` tag so origin stays discoverable.

References are NOT handled here — ``import_composition_references``
(in ``boot_import.py``) already wires those using path-based slugs.

Idempotent and additive: a slot/marker already present in an agent's
bindings is left alone. Existing bindings are preserved when new ones
are appended. ``config_json`` and ``agent_version_files`` are never
modified — bindings are an additive overlay.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from agentbox.core.data import SessionStore

logger = logging.getLogger(__name__)

USER_TEMPLATE_MARKER = "user_template"
USER_TEMPLATE_MODE = "inline"
MIGRATION_REASON = "boot: migrate composition slots to bindings"
MIGRATION_ACTOR = "composition_migration"


@dataclass
class CompositionMigrationReport:
    agents_migrated: list[str] = field(default_factory=list)
    agents_skipped_no_composition: list[str] = field(default_factory=list)
    agents_skipped_fully_bound: list[str] = field(default_factory=list)
    bindings_created: int = 0
    resources_created: int = 0
    versions_created: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "agents_migrated": len(self.agents_migrated),
            "agents_skipped_no_composition": len(self.agents_skipped_no_composition),
            "agents_skipped_fully_bound": len(self.agents_skipped_fully_bound),
            "bindings_created": self.bindings_created,
            "resources_created": self.resources_created,
            "versions_created": self.versions_created,
            "failed": len(self.failed),
        }


def _parse_tags(tags_field: str | None) -> list[str]:
    if not tags_field:
        return []
    try:
        parsed = json.loads(tags_field)
        if isinstance(parsed, list):
            return [str(t) for t in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return [t.strip() for t in str(tags_field).split(",") if t.strip()]


def _slug_for(type_: str, sha12: str) -> str:
    return f"migrated:{type_}:{sha12}"


def _mime_for(type_: str) -> str:
    return "application/json" if type_ == "schema" else "text/markdown"


def _get_or_create_resource(
    store: SessionStore,
    *,
    content_text: str,
    type_: str,
    relative_path: str,
    agent_id: str,
    report: CompositionMigrationReport,
) -> str:
    """Get-or-create a repo resource keyed by content hash. Returns resource_id."""
    content_bytes = content_text.encode("utf-8")
    sha_full = hashlib.sha256(content_bytes).hexdigest()
    sha12 = sha_full[:12]
    slug = _slug_for(type_, sha12)
    agent_tag = f"agent:{agent_id}"

    existing = store.get_repo_resource_by_slug(slug)
    if existing is not None:
        tags = _parse_tags(existing.get("tags"))
        if agent_tag not in tags:
            store.update_repo_resource(existing["id"], tags=[*tags, agent_tag])
        return existing["id"]

    pretty_kind = (
        "input schema"
        if "input_schema" in relative_path
        else "output schema"
        if "output_schema" in relative_path
        else relative_path
    )
    display = (
        f"{agent_id} {pretty_kind}"
        if type_ == "schema"
        else f"{agent_id} {relative_path}"
    )
    res = store.create_repo_resource(
        slug=slug,
        type=type_,
        display_name=display,
        description=f"Migrated from {agent_id}: {relative_path}",
        tags=["migrated", agent_tag],
        created_by=MIGRATION_ACTOR,
    )
    report.resources_created += 1
    store.import_repo_version(
        res["id"],
        [("", content_bytes, _mime_for(type_), content_text)],
        import_source="toml_migration",
        changelog="migrated from agent composition",
        source_metadata={
            "agent_id": agent_id,
            "relative_path": relative_path,
            "content_sha256": sha_full,
        },
        created_by=MIGRATION_ACTOR,
    )
    report.versions_created += 1
    return res["id"]


def _backfill_slot_active_flag(store: SessionStore) -> None:
    """Flip every existing slot binding to ``attach_as_reference=1``.

    Slots created before bundle deprecation defaulted the flag to 0; the
    new BindingsBundleSource gates rendering on it. Backfill makes the
    cutover safe.
    """
    with store.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE agent_prompt_resource_bindings "
                "SET attach_as_reference = 1 "
                "WHERE slot IS NOT NULL AND attach_as_reference = 0"
            )
        )


def _binding_to_input(b: dict) -> dict:
    """Convert a list_prompt_bindings row to a replace_prompt_bindings input dict."""
    return {
        "resource_id": b["resource_id"],
        "marker": b.get("marker"),
        "mode": b.get("mode"),
        "slot": b.get("slot"),
        "attach_as_reference": bool(b.get("attach_as_reference")),
        "pinned_version_id": b.get("pinned_version_id"),
        "required": bool(b.get("required")),
        "display_order": b.get("display_order", 0),
    }


def _read_disk_file(
    bundle_dir: Path | None,
    rel: str | None,
) -> str | None:
    """Best-effort read of a composition file from the agent's bundle dir."""
    if bundle_dir is None or not rel:
        return None
    candidate = bundle_dir / rel
    try:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    except OSError:
        logger.warning("composition migration: failed to read %s", candidate)
    return None


def _migrate_one_agent(
    store: SessionStore,
    agent_id: str,
    composition: dict,
    version_id: int,
    bundle_dir: Path | None,
    report: CompositionMigrationReport,
) -> bool:
    """Migrate one agent. Returns True if any bindings were added."""
    files = store.list_version_files(version_id)
    files_by_kind_path: dict[tuple[str, str], dict] = {}
    for f in files:
        files_by_kind_path[(f["kind"], f["relative_path"])] = f

    existing_bindings = store.list_prompt_bindings(agent_id)
    existing_slots = {b["slot"] for b in existing_bindings if b.get("slot")}
    existing_marker_pairs = {
        (b["resource_id"], b["marker"])
        for b in existing_bindings
        if b.get("marker") and not b.get("slot")
    }

    new_inputs = [_binding_to_input(b) for b in existing_bindings]
    next_order = (
        max((b.get("display_order", 0) for b in existing_bindings), default=-1) + 1
    )
    added = 0

    def _maybe_add_slot(slot: str, kind: str, type_: str) -> None:
        nonlocal next_order, added
        # System slot has no relative_path in composition — it's always
        # the agent's prompt file. Pick whatever the kind='system' row
        # offers in agent_version_files.
        if slot == "system":
            rel = composition.get("system") or composition.get("system_prompt")
        else:
            rel = composition.get(slot)
        if slot in existing_slots:
            return
        if not rel and slot != "system":
            return
        # For system, allow any kind='system' row regardless of rel.
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
            # Disk fallback: agent_version_files row missing but the
            # composition declares a path. Read directly from the bundle dir.
            disk_rel = rel or ("prompts/system.md" if slot == "system" else None)
            content_text = _read_disk_file(bundle_dir, disk_rel)
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
        resource_id = _get_or_create_resource(
            store,
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
                # All slot bindings are active by default. The runtime
                # gates rendering on attach_as_reference.
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
            disk_text = _read_disk_file(bundle_dir, user_template_rel)
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
            candidate_slug = _slug_for("document", sha12)
            existing = store.get_repo_resource_by_slug(candidate_slug)
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
                resource_id = _get_or_create_resource(
                    store,
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

    store.replace_prompt_bindings(
        agent_id,
        new_inputs,
        reason=MIGRATION_REASON,
        actor=MIGRATION_ACTOR,
    )
    report.bindings_created += added
    return True


def migrate_composition_to_bindings(
    store: SessionStore,
    *,
    only_agent_id: str | None = None,
    project_root: Path | None = None,
) -> CompositionMigrationReport:
    """Walk every agent's active version and migrate composition slots to bindings.

    Args:
        store: SessionStore.
        only_agent_id: When set, migrate only this agent (useful for CLI testing).

    Returns:
        A CompositionMigrationReport describing what happened.
    """
    report = CompositionMigrationReport()
    # Backfill: every pre-existing slot binding (input_schema /
    # output_schema, created when the runtime didn't gate on
    # attach_as_reference) needs the flag flipped to active so the
    # new BindingsBundleSource keeps rendering them.
    _backfill_slot_active_flag(store)
    agent_rows = store.list_agents_with_latest()

    for row in agent_rows:
        agent_id = row["agent_id"]
        if only_agent_id is not None and agent_id != only_agent_id:
            continue

        try:
            active = store.get_active_version(agent_id) or row
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
            # Every agent has at least a system prompt, so we always
            # attempt the migration — _migrate_one_agent is itself
            # idempotent and short-circuits when there is nothing to add.

            bundle_dir: Path | None = None
            if project_root is not None:
                src_path = active.get("source_path")
                if src_path:
                    candidate = (project_root / src_path).parent
                    if candidate.is_dir():
                        bundle_dir = candidate
            added = _migrate_one_agent(
                store,
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
