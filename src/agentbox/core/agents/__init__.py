"""Public facade for the Agents domain.

Re-exports the names available from `core.agent.*` so external callers can
import from one place instead of reaching into submodules.
"""

from agentbox.core.agents.composition.bundle.loader import (
    load_bundle_from_bindings as load_bundle_from_bindings,
)
from agentbox.core.agents.composition.capture import (
    build_fragments as build_fragments,
    fragments_to_json as fragments_to_json,
)
from agentbox.core.agents.composition.resolver import (
    resolve_prompt as resolve_prompt,
)
from agentbox.core.agents.config import (
    ExecutionConfig as ExecutionConfig,
    PythonAgentConfig as PythonAgentConfig,
    RuntimeConfig as RuntimeConfig,
    build_config_json_payload as build_config_json_payload,
)
from agentbox.core.agents.contract import (
    OutputConfig as OutputConfig,
    check_output as check_output,
    resolve_output_config as resolve_output_config,
    resolve_schema as resolve_schema,
)
from agentbox.core.agents.runtime import (
    build_runtime_view as build_runtime_view,
    capture_fragments as capture_fragments,
    compose_prompt as compose_prompt,
)
from agentbox.core.data.composition import (
    AgentRuntimeView as AgentRuntimeView,
    ComposedPrompt as ComposedPrompt,
    HttpValidatorConfig as HttpValidatorConfig,
    ScriptValidatorConfig as ScriptValidatorConfig,
    ValidationEngine as ValidationEngine,
    ValidationResult as ValidationResult,
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
    "build_runtime_view",
    "capture_fragments",
    "compose_prompt",
    "fragments_to_json",
    "load_bundle_from_bindings",
    "check_output",
    "resolve_output_config",
    "resolve_prompt",
    "resolve_schema",
]
