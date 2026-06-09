"""Output validation — re-export shim.

Moved to ``core.execution.validate`` in Plan 34.
This module exists for backward compatibility, re-exporting everything
from the ``validate`` package.
"""

from agentbox.core.execution.validate.errors import extract_json, format_jsonschema_error
from agentbox.core.execution.validate.gates import (
    call_http_validator,
    call_script_validator,
    run_json_schema,
    validate_jsonschema,
    validate_pydantic,
)
from agentbox.core.execution.validate.orchestrate import validate_output
from agentbox.core.execution.validate.pydantic import validate_with_pydantic
from agentbox.core.execution.validate.schema import (
    ValidationEngine,
    ValidationResult,
    resolve_schema,
)

__all__ = [
    "ValidationEngine",
    "ValidationResult",
    "call_http_validator",
    "call_script_validator",
    "extract_json",
    "format_jsonschema_error",
    "resolve_schema",
    "run_json_schema",
    "validate_jsonschema",
    "validate_output",
    "validate_pydantic",
    "validate_with_pydantic",
]
