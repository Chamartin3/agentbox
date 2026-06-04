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
from agentbox.core.agents.plugins import (
    backend_load_failure as backend_load_failure,
    backends as backends,
    get_backend as get_backend,
)
from agentbox.core.agents.profiles import (
    EffectiveRunnerConfig as EffectiveRunnerConfig,
    RunnerProfileResolver as RunnerProfileResolver,
)
from agentbox.core.agents.resolve import (
    engine_load_failure as engine_load_failure,
    list_engines as list_engines,
    resolve_engine as resolve_engine,
    resolve_engine_by_name as resolve_engine_by_name,
)

__all__ = [
    "EffectiveRunnerConfig",
    "ExecutionConfig",
    "HttpValidatorConfig",
    "OutputConfig",
    "PythonAgentConfig",
    "RunnerProfileResolver",
    "RuntimeConfig",
    "ScriptValidatorConfig",
    "build_config_json_payload",
    "build_fragments",
    "fragments_to_json",
    "backend_load_failure",
    "backends",
    "engine_load_failure",
    "get_backend",
    "list_engines",
    "load_bundle_from_bindings",
    "resolve_engine",
    "resolve_engine_by_name",
    "resolve_output_config",
    "resolve_prompt",
    "_append_output_contract",
]
