"""Pydantic-model helpers for dynamic validation from JSON Schema.

Delegates model construction to the canonical
``engines.contracts.schema_to_model.json_schema_to_pydantic_model``
so there is exactly one JSON-Schema→pydantic transform in the codebase.
"""

from __future__ import annotations

import json
from typing import Any

from agentbox.core.agents.validation.errors import extract_json
from agentbox.core.engines.contracts.schema_to_model.translate import (
    json_schema_to_pydantic_model,
)


def validate_with_pydantic(
    output_text: str,
    schema: dict[str, Any],
) -> tuple[bool, str]:
    """Validate *output_text* against *schema* using a dynamic pydantic model.

    Returns ``(True, "")`` on success or ``(False, error_message)`` on
    failure.  The error message is a concise pydantic-style string.
    """
    try:
        instance = json.loads(extract_json(output_text))
    except json.JSONDecodeError as exc:
        return False, f"output is not valid JSON: {exc}"

    try:
        model = json_schema_to_pydantic_model(schema, model_name="OutputModel")
    except Exception as exc:
        return False, f"cannot build pydantic model from schema: {exc}"

    try:
        model.model_validate(instance)
        return True, ""
    except Exception as exc:
        return False, str(exc)


__all__ = ["validate_with_pydantic"]
