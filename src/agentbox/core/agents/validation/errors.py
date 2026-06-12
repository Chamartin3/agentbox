"""Error-formatting and JSON-extraction helpers for output validation."""

from __future__ import annotations

import json
import re

import jsonschema as _jsonschema

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull a JSON payload out of prose-wrapped model output.

    Models often wrap JSON in ``` fences plus surrounding prose despite
    being told not to. Validation should still engage on the JSON they
    produced, so we extract the first fenced block when present, then
    fall back to the first ``{...}`` / ``[...]`` slice, then return the
    raw text unchanged for ``json.loads`` to fail on naturally.
    """
    if not text:
        return text
    m = _FENCED_JSON_RE.search(text)
    if m:
        return m.group(1).strip()
    s = text.strip()
    if s.startswith(("{", "[")):
        return s
    for opener, closer in (("{", "}"), ("[", "]")):
        i = s.find(opener)
        j = s.rfind(closer)
        if 0 <= i < j:
            return s[i : j + 1]
    return s


def format_jsonschema_error(exc: _jsonschema.ValidationError) -> str:
    """Render a jsonschema error so the agent sees *where* it failed.

    The default ``str(exc)`` dumps the schema + instance but doesn't say
    *which JSON pointer path* the failing validator was anchored at —
    agents reading the error try to fix the wrong place. We surface the
    instance path, schema path, sub-errors for ``oneOf``, and a truncated
    instance preview so the retry prompt is actionable.
    """
    instance_pointer = (
        "/" + "/".join(str(p) for p in exc.absolute_path) if exc.absolute_path else "/"
    )
    schema_pointer = (
        "/" + "/".join(str(p) for p in exc.absolute_schema_path)
        if exc.absolute_schema_path
        else "/"
    )
    lines = [
        f"validation failed at instance path: {instance_pointer}",
        f"schema rule violated at: {schema_pointer} ({exc.validator})",
        f"message: {exc.message}",
    ]
    if exc.validator == "oneOf" and exc.context:
        lines.append("")
        lines.append("oneOf sub-errors (each branch's first failure):")
        for branch_idx, sub in enumerate(exc.context):
            title = ""
            try:
                title = (
                    sub.schema.get("title", "") if isinstance(sub.schema, dict) else ""
                )
            except AttributeError:
                title = ""
            label = f"branch[{branch_idx}]"
            if title:
                label += f" ({title})"
            sub_path = (
                "/" + "/".join(str(p) for p in sub.absolute_path)
                if sub.absolute_path
                else "/"
            )
            lines.append(f"  - {label} at {sub_path}: {sub.message}")
    try:
        instance_preview = json.dumps(exc.instance, default=str)
    except (TypeError, ValueError):
        instance_preview = repr(exc.instance)
    if len(instance_preview) > 800:
        instance_preview = instance_preview[:800] + "...(truncated)"
    lines.append(f"instance preview: {instance_preview}")
    return "\n".join(lines)
