"""Parity matrix tests for built-in tools taxonomy (Plan 08 Phase 10)."""

from __future__ import annotations

import pytest
from agentbox.core.infra.builtin_tools.registry import (
    BUILTIN_TOOLS,
    BuiltinToolSpec,
    backend_tool_name,
    get_builtin,
)


class TestRegistry:
    def test_all_tools_have_names(self):
        for tool in BUILTIN_TOOLS:
            assert tool.name, f"tool missing name: {tool!r}"

    def test_no_duplicate_names(self):
        names = [t.name for t in BUILTIN_TOOLS]
        assert len(names) == len(set(names)), "duplicate tool names"

    def test_get_builtin_returns_spec(self):
        spec = get_builtin("fs.read")
        assert isinstance(spec, BuiltinToolSpec)
        assert spec.name == "fs.read"

    def test_get_builtin_returns_none_for_unknown(self):
        assert get_builtin("nonexistent.tool") is None

    def test_capability_alignment(self):
        """Tools with a capability must have the same name as the capability key."""
        from agentbox.core.infra.host_env.capabilities import CAPABILITIES

        for tool in BUILTIN_TOOLS:
            if tool.capability is not None:
                assert tool.capability in CAPABILITIES, (
                    f"{tool.name}: capability {tool.capability!r} not in CAPABILITIES"
                )


class TestBackendNames:
    @pytest.mark.parametrize(
        "tool_name,runner,expected",
        [
            ("fs.read", "claude_code", "Read"),
            ("fs.write", "claude_code", "Write"),
            ("fs.list", "claude_code", "LS"),
            ("shell.exec", "claude_code", "Bash"),
            ("http.fetch", "claude_code", "WebFetch"),
            ("web.search", "claude_code", "WebSearch"),
            ("fs.read", "opencode", "read_file"),
            ("fs.write", "opencode", "write_file"),
            ("shell.exec", "opencode", "run_command"),
        ],
    )
    def test_parity_matrix(self, tool_name: str, runner: str, expected: str):
        result = backend_tool_name(tool_name, runner)
        assert result == expected, (
            f"{tool_name} → {runner}: expected {expected!r}, got {result!r}"
        )

    def test_unknown_tool_returns_none(self):
        assert backend_tool_name("no.such.tool", "claude_code") is None

    def test_unknown_backend_returns_none(self):
        assert backend_tool_name("fs.read", "unknown_backend") is None
