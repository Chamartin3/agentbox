"""Output contract — schema resolution, prompt rendering, output checking.

Public surface for the Agents contract sub-package (pulled from validation,
composition, and config).
"""

from agentbox.core.agents.contract.check import (
    call_http_validator,
    call_script_validator,
    check_output,
    format_jsonschema_error,
    run_json_schema,
    validate_jsonschema,
    validate_pydantic,
)
from agentbox.core.agents.contract.render import (
    append,
    append_input_schema,
    append_schema,
    append_validation_engine_hint,
    render,
)
from agentbox.core.agents.contract.schema import (
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
    "append",
    "append_input_schema",
    "append_schema",
    "append_validation_engine_hint",
    "call_http_validator",
    "call_script_validator",
    "check_output",
    "format_jsonschema_error",
    "render",
    "resolve_output_config",
    "resolve_schema",
    "run_json_schema",
    "validate_jsonschema",
    "validate_pydantic",
]
