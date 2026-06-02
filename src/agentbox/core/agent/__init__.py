"""Public facade for the Agents domain.

Re-exports the names available from `core.agent.*` so external callers can
import from one place instead of reaching into submodules. Concrete public
surface is finalized in Phase 8; this facade exposes what exists today.
"""

from agentbox.core.agent.config import (
    ExecutionConfig as ExecutionConfig,
    HttpValidatorConfig as HttpValidatorConfig,
    OutputConfig as OutputConfig,
    PythonAgentConfig as PythonAgentConfig,
    RuntimeConfig as RuntimeConfig,
    ScriptValidatorConfig as ScriptValidatorConfig,
    build_config_json_payload as build_config_json_payload,
    resolve_output_config as resolve_output_config,
)
from agentbox.core.agent.plugins import (
    backend_load_failure as backend_load_failure,
    backends as backends,
    get_backend as get_backend,
)
from agentbox.core.agent.resolve import (
    engine_load_failure as engine_load_failure,
    list_engines as list_engines,
    resolve_engine_by_name as resolve_engine_by_name,
)

__all__ = [
    "ExecutionConfig",
    "HttpValidatorConfig",
    "OutputConfig",
    "PythonAgentConfig",
    "RuntimeConfig",
    "ScriptValidatorConfig",
    "backend_load_failure",
    "backends",
    "build_config_json_payload",
    "engine_load_failure",
    "get_backend",
    "list_engines",
    "resolve_engine_by_name",
    "resolve_output_config",
]
