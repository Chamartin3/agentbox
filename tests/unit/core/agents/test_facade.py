"""Guard: the agents domain is reached through its ``__init__`` facade only.

Complements the ``agents-facade`` import-linter contract (which enforces the
*import direction* — outside code must not deep-import ``core.agents.*``
submodules). This test guards the facade's own health: no dangling ``__all__``
entry, the load-bearing verbs stay present, and the mechanism-named packages
retired by plan 120 (``composition`` / ``config``) do not come back.
"""

from __future__ import annotations

import importlib

import pytest

import agentbox.core.agents as agents

# One verb per concept-component, so a rename that forgets the facade fails here.
REQUIRED_SURFACE = (
    "build_prompt",          # prompt/
    "build_runtime_view",    # prompt/
    "resolve_agent_prompt_bindings",  # prompt/
    "check_output",          # contract/
    "resolve_schema",        # contract/
    "resolve_output_config",  # contract/
    "ExecutionConfig",       # definition/
    "RuntimeConfig",         # definition/
    "build_config_json_payload",  # definition/
    "resolve_engine",        # runner
    "list_engines",          # runner
    "check_drift",           # versioning/
    "startup_sweep",         # versioning/
    "PromptDoc",             # versioning/
)

RETIRED_PACKAGES = (
    "agentbox.core.agents.composition",
    "agentbox.core.agents.config",
    "agentbox.core.agents.validation",
    "agentbox.core.agents.runtime",
)


def test_all_entries_resolve() -> None:
    """Every name in ``__all__`` is actually importable from the facade."""
    missing = [name for name in agents.__all__ if not hasattr(agents, name)]
    assert not missing, f"dangling __all__ entries: {missing}"


def test_required_surface_present() -> None:
    absent = [name for name in REQUIRED_SURFACE if not hasattr(agents, name)]
    assert not absent, f"facade lost load-bearing verbs: {absent}"


@pytest.mark.parametrize("mod", RETIRED_PACKAGES)
def test_retired_packages_stay_dead(mod: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(mod)


if __name__ == "__main__":
    test_all_entries_resolve()
    test_required_surface_present()
    for _m in RETIRED_PACKAGES:
        try:
            importlib.import_module(_m)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{_m} should be gone")
    print("agents facade guard: OK")
