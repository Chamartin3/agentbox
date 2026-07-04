"""MCP tools for prompt resource bindings (attach / detach / list / set)."""

from __future__ import annotations

from fastmcp import FastMCP

from agentbox.core.data.payload_types import PromptBindingSpec
from agentbox.core.data.rows import AgentPromptBindingRow
from agentbox.mcp.context import MCPContext


def _require_reason(reason: str) -> dict | None:
    if not reason or len(reason.strip()) < 3:
        return {
            "error": "reason_too_short",
            "detail": "reason must be at least 3 characters",
        }
    return None


def register_bindings(mcp: FastMCP, ctx: MCPContext) -> None:
    @mcp.tool
    def get_prompt_resources(agent_id: str) -> dict:
        """List the prompt resource bindings currently attached to an agent.

        Each item includes the binding id (use it for ``unbind_prompt_resource``),
        marker, mode, slot, ``attach_as_reference`` flag, pinned version, and
        enriched resource metadata (slug, type, display_name, active_version_id).
        Mirrors ``GET /api/agents/{agent_id}/prompt-resources``."""
        svc = ctx.resources
        enriched = svc.list_prompt_resources(agent_id)["items"]
        return {"agent_id": agent_id, "items": enriched, "count": len(enriched)}

    @mcp.tool
    def set_prompt_resources(
        agent_id: str,
        bindings: list[PromptBindingSpec],
        reason: str,
    ) -> dict:
        """Replace all prompt resource bindings for an agent (atomic).

        Each binding: ``{resource_id, marker?, mode?, slot?,
        attach_as_reference?, pinned_version_id?, required?, display_order?}``.
        Pass an empty list to clear all bindings. ``reason`` ≥ 3 chars.

        For incremental edits prefer ``bind_prompt_resource`` /
        ``unbind_prompt_resource`` so you don't have to re-send the full list."""
        err = _require_reason(reason)
        if err:
            return err
        svc = ctx.resources
        try:
            rows = svc.replace_prompt_bindings(agent_id, bindings, reason=reason)
        except ValueError as exc:
            return {"error": "invalid_binding", "detail": str(exc)}
        return {"agent_id": agent_id, "bindings": rows, "count": len(rows)}

    @mcp.tool
    def bind_prompt_resource(
        agent_id: str,
        resource_id: str,
        reason: str,
        marker: str | None = None,
        mode: str | None = None,
        slot: str | None = None,
        attach_as_reference: bool = False,
        pinned_version_id: str | None = None,
        required: bool = True,
        display_order: int | None = None,
    ) -> dict:
        """Attach a single resource to an agent's prompt (incremental).

        Reads the current bindings, appends one, and writes the set back
        atomically. ``reason`` ≥ 3 chars.

        Provide ``marker`` + ``mode`` for splice bindings, ``slot`` for
        system/user_template/input_schema/output_schema bindings, or
        neither (with ``attach_as_reference=True``) for a reference-only
        binding appended under ``## References``."""
        err = _require_reason(reason)
        if err:
            return err
        svc = ctx.resources
        current = svc.list_prompt_bindings(agent_id)
        existing: list[PromptBindingSpec] = [
            {
                "resource_id": b["resource_id"],
                "marker": b.get("marker"),
                "mode": b.get("mode"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "pinned_version_id": b.get("pinned_version_id"),
                "required": bool(b.get("required", 1)),
                "display_order": int(b.get("display_order", 0)),
            }
            for b in current
        ]
        next_order = (
            display_order
            if display_order is not None
            else (max((b.get("display_order", 0) for b in existing), default=-1) + 1)
        )
        new_binding: PromptBindingSpec = {
            "resource_id": resource_id,
            "marker": marker,
            "mode": mode,
            "slot": slot,
            "attach_as_reference": attach_as_reference,
            "pinned_version_id": pinned_version_id,
            "required": required,
            "display_order": next_order,
        }
        try:
            rows = svc.replace_prompt_bindings(
                agent_id, [*existing, new_binding], reason=reason
            )
        except ValueError as exc:
            return {"error": "invalid_binding", "detail": str(exc)}
        added = next(
            (
                r
                for r in rows
                if r["resource_id"] == resource_id
                and r.get("marker") == new_binding["marker"]
                and r.get("slot") == new_binding["slot"]
                and int(r.get("display_order", -1)) == next_order
            ),
            None,
        )
        return {
            "agent_id": agent_id,
            "added": added,
            "bindings": rows,
            "count": len(rows),
        }

    @mcp.tool
    def unbind_prompt_resource(
        agent_id: str,
        reason: str,
        binding_id: str | None = None,
        resource_id: str | None = None,
        marker: str | None = None,
        slot: str | None = None,
    ) -> dict:
        """Detach prompt resource binding(s) from an agent (incremental).

        Identify what to remove by EITHER ``binding_id`` (most specific)
        OR a filter of ``resource_id`` / ``marker`` / ``slot`` (any
        combination — all provided fields must match). At least one
        identifier is required. ``reason`` ≥ 3 chars."""
        err = _require_reason(reason)
        if err:
            return err
        if not any([binding_id, resource_id, marker, slot]):
            return {
                "error": "invalid_request",
                "detail": "provide binding_id, or any of resource_id/marker/slot",
            }
        svc = ctx.resources
        current = svc.list_prompt_bindings(agent_id)

        def _matches(b: AgentPromptBindingRow) -> bool:
            if binding_id is not None:
                return b["id"] == binding_id
            if resource_id is not None and b["resource_id"] != resource_id:
                return False
            if marker is not None and b.get("marker") != marker:
                return False
            return not (slot is not None and b.get("slot") != slot)

        removed = [b for b in current if _matches(b)]
        if not removed:
            return {"error": "not_found", "agent_id": agent_id, "removed": []}

        keep: list[PromptBindingSpec] = [
            {
                "resource_id": b["resource_id"],
                "marker": b.get("marker"),
                "mode": b.get("mode"),
                "slot": b.get("slot"),
                "attach_as_reference": bool(b.get("attach_as_reference")),
                "pinned_version_id": b.get("pinned_version_id"),
                "required": bool(b.get("required", 1)),
                "display_order": int(b.get("display_order", 0)),
            }
            for b in current
            if not _matches(b)
        ]
        try:
            rows = svc.replace_prompt_bindings(agent_id, keep, reason=reason)
        except ValueError as exc:
            return {"error": "invalid_binding", "detail": str(exc)}
        return {
            "agent_id": agent_id,
            "removed": [
                {
                    "binding_id": b["id"],
                    "resource_id": b["resource_id"],
                    "marker": b.get("marker"),
                    "slot": b.get("slot"),
                }
                for b in removed
            ],
            "bindings": rows,
            "count": len(rows),
        }
