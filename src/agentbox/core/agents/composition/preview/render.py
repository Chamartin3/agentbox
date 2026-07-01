"""Main render_agent_prompt_preview entry point."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentbox.core.agents.composition.resolver import resolve_prompt
from agentbox.core.agents.composition.preview._helpers import (
    PreviewError,
    _render_references_block,
    _resolve_binding,
    _schema_block,
    _schema_for_slot,
    _validation_block_for_preview,
)

if TYPE_CHECKING:
    from agentbox.core.db import (
        AgentPromptResourceBindingManager,
        AgentVersionManager,
        ResourceBlobManager,
        ResourceManager,
        ResourceVersionManager,
    )


def render_agent_prompt_preview(
    agent_versions: AgentVersionManager,
    resource_versions: ResourceVersionManager,
    resource_blobs: ResourceBlobManager,
    resources: ResourceManager,
    agent_prompt_resource_bindings: AgentPromptResourceBindingManager,
    *,
    agent_id: str,
    template: str | None = None,
    bindings_override: list[dict] | None = None,
) -> dict:
    """Render the full composed prompt for an agent.

    If ``bindings_override`` is provided, use it instead of the live
    ``agent_prompt_resource_bindings`` rows for the agent. The override
    list uses the same shape as the input to ``replace_prompt_bindings``.

    On success returns a dict with keys:
        rendered_prompt, base_prompt, template, unresolved_markers,
        warnings, references, input_schema, output_schema,
        raw_text_output, char_breakdown, total_chars, snapshot.

    On binding-resolution failure raises ``PreviewError``.
    """
    if template is None:
        row = agent_versions.get_active(agent_id) or agent_versions.get_latest(agent_id)
        if row is None:
            raise PreviewError(
                "no_agent_version",
                f"no prompt version for agent {agent_id!r}",
            )
        template = row.get("prompt_content") or ""

    if bindings_override is not None:
        raw = [
            {**b, "id": b.get("id") or f"preview-{i}"}
            for i, b in enumerate(bindings_override)
        ]
    else:
        raw = agent_prompt_resource_bindings.list_for_agent(agent_id)

    resolved = [_resolve_binding(resources, resource_versions, resource_blobs, b) for b in raw]

    # DB-as-source-of-truth: ``agent_versions.prompt_content`` (passed in
    # as ``template``) is the only system-prompt source. Legacy
    # ``slot='system'`` bindings are ignored at render time — they remain
    # in the table for history but never shadow live ``edit_prompt`` edits.
    splice_bindings = [b for b in resolved if b.get("marker") and b.get("mode")]
    result = resolve_prompt(template, splice_bindings)

    refs_text, refs_meta, per_ref_chars = _render_references_block(resolved)
    base_prompt = result.rendered_prompt
    composed = base_prompt

    input_schema = _schema_for_slot(resolved, "input_schema")
    output_schema = _schema_for_slot(resolved, "output_schema")
    raw_text_output = output_schema is None

    input_schema_block = _schema_block("input_schema", input_schema)
    if input_schema_block:
        composed = composed.rstrip() + "\n\n" + input_schema_block

    if refs_text:
        composed = composed.rstrip() + "\n\n" + refs_text

    output_schema_block = _schema_block("output_schema", output_schema)
    if output_schema_block:
        composed = composed.rstrip() + "\n\n" + output_schema_block

    # Validation contract — rules + a short validators hint, mirroring
    # what core/prompt/output_contract.append() does at runtime so the
    # preview reflects what the model actually sees. The schema piece is
    # intentionally omitted (already rendered above from the binding).
    validation_block, validation_view = _validation_block_for_preview(agent_versions, resources, agent_id)
    if validation_block:
        composed = composed.rstrip() + "\n\n" + validation_block

    parts: list[dict] = [
        {"label": "prompt template", "chars": len(base_prompt)},
    ]
    if input_schema_block and input_schema is not None:
        parts.append(
            {
                "label": "input_schema block",
                "chars": len(input_schema_block) + 2,
                "binding_id": input_schema["binding_id"],
                "resource_id": input_schema["resource_id"],
                "version_id": input_schema["version_id"],
            }
        )
    if refs_text:
        parts.extend(per_ref_chars)
    # Validator-sourced blocks share the "validator:" prefix so they're
    # visually grouped in the composer breakdown chart — schema (implicit
    # validator), rules, and the validation hint all originate from the
    # validation contract surface.
    if output_schema_block and output_schema is not None:
        parts.append(
            {
                "label": "validator: output schema (json-schema gate)",
                "kind": "validator",
                "chars": len(output_schema_block) + 2,
                "binding_id": output_schema["binding_id"],
                "resource_id": output_schema["resource_id"],
                "version_id": output_schema["version_id"],
            }
        )
    if validation_block:
        parts.append(
            {
                "label": "validator: constraints + post-hoc validators",
                "kind": "validator",
                "chars": len(validation_block) + 2,
            }
        )

    return {
        "rendered_prompt": composed,
        "base_prompt": base_prompt,
        "template": template,
        "unresolved_markers": result.unresolved_markers,
        "warnings": result.warnings,
        "references": refs_meta,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "validation": validation_view,
        "raw_text_output": raw_text_output,
        "char_breakdown": parts,
        "total_chars": len(composed),
        "snapshot": [
            {
                "binding_id": rb.binding_id,
                "marker": rb.marker,
                "resource_id": rb.resource_id,
                "version_id": rb.version_id,
                "content_hash": rb.content_hash,
                "mode": rb.mode,
                "chars": len(rb.rendered),
            }
            for rb in result.snapshot
        ],
    }
