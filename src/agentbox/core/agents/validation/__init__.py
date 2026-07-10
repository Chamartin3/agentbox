"""Output contract — validation only: schema resolution + output checking.

Public surface for the Agents contract sub-package. Rendering the contract
INTO prompt text is a composition responsibility and lives in
``core.agents.composition.rendering``, not here.
"""

from agentbox.core.agents.validation.check import (
    call_http_validator,
    call_script_validator,
    check_output,
    format_jsonschema_error,
    run_json_schema,
    validate_jsonschema,
    validate_pydantic,
)
from agentbox.core.agents.validation.schema import (
    OutputConfig,
    resolve_output_config,
    resolve_schema,
)
from agentbox.core.data.composition import (
    ValidationEngine,
    ValidationResult,
)

__all__ = [
    "OutputConfig",
    "ValidationEngine",
    "ValidationResult",
    "call_http_validator",
    "call_script_validator",
    "check_output",
    "format_jsonschema_error",
    "resolve_output_config",
    "resolve_schema",
    "run_json_schema",
    "validate_jsonschema",
    "validate_pydantic",
]
