"""Validate that a value is a structurally-valid JSON Schema.

Shared by every layer that ingests a schema — the agents composition
loader (schemas read from bundle files) and the workspaces MCP transport
(schemas received off the wire from a third-party MCP server). Both must
reject a syntactically-fine-but-structurally-broken schema *at the
boundary* rather than assert ``JsonSchemaDict`` on unvalidated input.

Lives in ``core.data`` (the shared leaf) because ``agents`` and
``workspaces`` are independent peers and neither may import the other.
``jsonschema`` is a permitted third-party dependency here.
"""

from __future__ import annotations

import json
from typing import cast

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

from agentbox.core.data.errors.schemas import UnsupportedSchema
from agentbox.core.data.payload_types import JsonSchemaDict
from agentbox.core.data.schema_consistency import assert_schema_consistent


def validate_json_schema(obj: object) -> JsonSchemaDict:
    """Validate an already-parsed value is a structurally-valid JSON Schema.

    Raises ``jsonschema.exceptions.SchemaError`` when *obj* is not a usable
    JSON Schema — wrong root type, an invalid keyword per its declared draft,
    or a ``required``/``properties`` inconsistency.
    """
    if not isinstance(obj, dict):
        raise SchemaError(
            f"JSON Schema root must be an object, got {type(obj).__name__}"
        )
    # 1. valid per its declared draft (``validator_for`` reads ``$schema``,
    #    defaulting to the latest draft when absent).
    validator_for(obj).check_schema(obj)
    # 2. the codebase's required-subset-of-properties invariant. Normalise its
    #    InconsistentSchema/UnsupportedSchema into SchemaError so every caller
    #    handles one exception type for "not a usable schema".
    try:
        assert_schema_consistent(obj)
    except UnsupportedSchema as exc:
        raise SchemaError(str(exc)) from exc
    # ``obj`` is now runtime-proven. This is the one sanctioned cast
    # (type-safety §6: cast a *validated* input to its concrete type).
    return cast("JsonSchemaDict", obj)


def load_json_schema(text: str) -> JsonSchemaDict:
    """Parse *text* as JSON and validate it is a structurally-valid JSON Schema.

    Raises ``json.JSONDecodeError`` on malformed JSON and
    ``jsonschema.exceptions.SchemaError`` on an invalid schema.
    """
    return validate_json_schema(json.loads(text))
