"""Public facade for the Agents domain.

Re-exports the names available from `core.agent.*` so external callers can
import from one place instead of reaching into submodules.
"""

from agentbox.core.agents.composition.bundle import (
    _append_validation_engine_hint as _append_validation_engine_hint,
)
from agentbox.core.agents.composition.bundle.loader import (
    load_bundle_from_bindings as load_bundle_from_bindings,
)
from agentbox.core.agents.composition.capture import (
    build_fragments as build_fragments,
    fragments_to_json as fragments_to_json,
)
from agentbox.core.agents.composition.output_contract import (
    append as _append_output_contract,
)
from agentbox.core.agents.composition.resolver import (
    resolve_prompt as resolve_prompt,
)
from agentbox.core.agents.config import (
    ExecutionConfig as ExecutionConfig,
    HttpValidatorConfig as HttpValidatorConfig,
    OutputConfig as OutputConfig,
    PythonAgentConfig as PythonAgentConfig,
    RuntimeConfig as RuntimeConfig,
    ScriptValidatorConfig as ScriptValidatorConfig,
    build_config_json_payload as build_config_json_payload,
    resolve_output_config as resolve_output_config,
)
from agentbox.core.agents.runtime import (
    AgentRuntimeView as AgentRuntimeView,
    ComposedPrompt as ComposedPrompt,
    capture_fragments as capture_fragments,
    compose_prompt as compose_prompt,
)
from agentbox.core.agents.validation import (
    ValidationEngine as ValidationEngine,
    ValidationResult as ValidationResult,
    resolve_schema as resolve_schema,
    validate_output as validate_output,
)

__all__ = [
    "AgentRuntimeView",
    "ComposedPrompt",
    "ExecutionConfig",
    "HttpValidatorConfig",
    "OutputConfig",
    "PythonAgentConfig",
    "RuntimeConfig",
    "ScriptValidatorConfig",
    "ValidationEngine",
    "ValidationResult",
    "build_config_json_payload",
    "build_fragments",
    "capture_fragments",
    "compose_prompt",
    "fragments_to_json",
    "load_bundle_from_bindings",
    "resolve_output_config",
    "resolve_prompt",
    "resolve_schema",
    "validate_output",
    "_append_output_contract",
]
