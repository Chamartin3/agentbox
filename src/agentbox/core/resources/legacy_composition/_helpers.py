"""Helper functions for composition-to-bindings migration."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import text

from agentbox.core.db import AgentPromptResourceBindingManager

logger = logging.getLogger(__name__)


def parse_tags(tags_field: str | None) -> list[str]:
    if not tags_field:
        return []
    try:
        parsed = json.loads(tags_field)
        if isinstance(parsed, list):
            return [str(t) for t in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return [t.strip() for t in str(tags_field).split(",") if t.strip()]


def slug_for(type_: str, sha12: str) -> str:
    return f"migrated:{type_}:{sha12}"


def mime_for(type_: str) -> str:
    return "application/json" if type_ == "schema" else "text/markdown"


def read_disk_file(
    bundle_dir: Path | None,
    rel: str | None,
) -> str | None:
    if bundle_dir is None or not rel:
        return None
    candidate = bundle_dir / rel
    try:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    except OSError:
        logger.warning("composition migration: failed to read %s", candidate)
    return None


def binding_to_input(b: dict) -> dict:
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


def backfill_slot_active_flag(prompt_bindings: AgentPromptResourceBindingManager) -> None:
    with prompt_bindings._engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE agent_prompt_resource_bindings "
                "SET attach_as_reference = 1 "
                "WHERE slot IS NOT NULL AND attach_as_reference = 0"
            )
        )
