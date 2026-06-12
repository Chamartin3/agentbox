"""Output validation — schema gates, error formatting, and retry orchestration.

Public surface for the Agents validation sub-package.
"""

from agentbox.core.agents.validation.errors import (
    extract_json,
    format_jsonschema_error,
)
from agentbox.core.agents.validation.gates import (
    call_http_validator,
    call_script_validator,
    run_json_schema,
    validate_jsonschema,
    validate_pydantic,
)
from agentbox.core.agents.validation.orchestrate import validate_output
from agentbox.core.agents.validation.pydantic import validate_with_pydantic
from agentbox.core.agents.validation.schema import (
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
