"""Regression guard for the ``agentbox.cli.shared`` surface.

The shared surface is the canonical import path for CLI infrastructure.
If a name disappears from ``__all__`` (or stops being importable), call
sites break. This test freezes the expected exports so the surface cannot
silently regrow.
"""

from __future__ import annotations

import agentbox.cli.shared as shared


EXPECTED_EXPORTS: frozenset[str] = frozenset({
    # context — DI + error contract
    "CLIContext",
    "Renderers",
    "build_ctx",
    "group_callback",
    "handle_cli_errors",
    "resolve_agent",
    # constants
    "CLI_AUTHOR",
    "CLI_SOURCE",
    "EPHEMERAL_WORKSPACE",
    "EVENT_STYLES",
    "NA",
    "RUNNER_CLEAR",
    "Style",
    # render — base class
    "Renderer",
    # renderers — per-domain components
    "AgentRenderer",
    "EngineRenderer",
    "OpsRenderer",
    "RunRenderer",
    "SystemRenderer",
    "WorkspaceRenderer",
    # deps — documented exceptions (consumers not yet migrated to ctx.obj)
    "get_executor",
    "get_mcp_registry",
})


def test_all_matches_expected() -> None:
    actual = frozenset(shared.__all__)
    removed = EXPECTED_EXPORTS - actual
    added = actual - EXPECTED_EXPORTS
    assert not removed, f"shared surface lost exports: {sorted(removed)}"
    assert not added, (
        f"shared surface gained exports without updating this test: {sorted(added)}"
    )


def test_every_export_is_importable() -> None:
    missing = [name for name in shared.__all__ if not hasattr(shared, name)]
    assert not missing, f"declared in __all__ but not present on module: {missing}"
