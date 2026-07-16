"""Load + validate a JSON Schema document from text.

Agent input/output schemas are read from bundle files and agent config.
Historically we ``json.loads``-ed them and assigned straight into a
``JsonSchemaDict`` — so a syntactically-fine-but-structurally-broken schema
(e.g. ``required`` referencing an undeclared property, or a non-object at the
root) slipped through until it blew up much later at the executor's pydantic
conversion. This module validates at the load boundary instead.

Two checks:
1. ``jsonschema`` meta-schema validation — the document is a valid JSON Schema
   for its declared (or latest) draft.
2. ``assert_schema_consistent`` — the codebase's own gate (``required`` ⊆
   ``properties`` at every level), which the token backend also enforces.
"""

from __future__ import annotations

import json
from typing import cast

from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for

from agentbox.core.data import JsonSchemaDict, assert_schema_consistent
from agentbox.core.data.errors.schemas import UnsupportedSchema


def load_json_schema(text: str) -> JsonSchemaDict:
    """Parse *text* as JSON and validate it is a structurally-valid JSON Schema.

    Raises ``json.JSONDecodeError`` on malformed JSON and
    ``jsonschema.exceptions.SchemaError`` when the document is not a valid
    JSON Schema (wrong root type, unknown-keyword misuse, or an inconsistent
    ``required``/``properties`` relationship).
    """
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise SchemaError(
            f"JSON Schema root must be an object, got {type(obj).__name__}"
        )
    # 1. valid per its declared draft (validator_for reads ``$schema``,
    #    defaulting to the latest draft when absent).
    validator_for(obj).check_schema(obj)
    # 2. the codebase's required-subset-of-properties invariant. Normalise its
    #    InconsistentSchema/UnsupportedSchema into SchemaError so every caller
    #    handles one exception type for "not a usable schema".
    try:
        assert_schema_consistent(obj)
    except UnsupportedSchema as exc:
        raise SchemaError(str(exc)) from exc
    # ``obj`` is now runtime-proven: an object root, valid for its draft, and
    # internally consistent. This is the one sanctioned cast (type-safety §6:
    # cast a *validated* input to its concrete type) — the whole function exists
    # to earn it.
    return cast("JsonSchemaDict", obj)
