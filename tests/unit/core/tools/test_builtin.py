"""Parity matrix tests for built-in tools taxonomy (Plan 08 Phase 10)."""

from __future__ import annotations

import pytest
from agentbox.core.tools.builtin import (
    BUILTIN_TOOLS,
    BuiltinToolSpec,
    get_builtin,
)
from agentbox.core.tools.translation import translate_tool
from agentbox.core.engines.backends.claude_code.tools import (
    NATIVE_TOOLS as CLAUDE_TOOLS,
)
from agentbox.core.engines.backends.opencode.tools import (
    NATIVE_TOOLS as OPENCODE_TOOLS,
)
from agentbox.core.tools import CAPABILITIES


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
        for tool in BUILTIN_TOOLS:
            if tool.capability is not None:
                assert tool.capability in CAPABILITIES, (
                    f"{tool.name}: capability {tool.capability!r} not in CAPABILITIES"
                )


class TestBackendNames:
    @pytest.mark.parametrize(
        "tool_name,native_map,expected",
        [
            ("fs.read", CLAUDE_TOOLS, "Read"),
            ("fs.write", CLAUDE_TOOLS, "Write"),
            ("fs.list", CLAUDE_TOOLS, "LS"),
            ("shell.exec", CLAUDE_TOOLS, "Bash"),
            ("http.fetch", CLAUDE_TOOLS, "WebFetch"),
            ("web.search", CLAUDE_TOOLS, "WebSearch"),
            ("fs.read", OPENCODE_TOOLS, "read"),
            ("fs.write", OPENCODE_TOOLS, "write"),
            ("shell.exec", OPENCODE_TOOLS, "bash"),
        ],
    )
    def test_parity_matrix(
        self, tool_name: str, native_map: dict, expected: str
    ):
        result = translate_tool(tool_name, native_map)
        assert result == expected, (
            f"{tool_name}: expected {expected!r}, got {result!r}"
        )

    def test_unknown_tool_passthrough(self):
        assert translate_tool("no.such.tool", CLAUDE_TOOLS) == "no.such.tool"

    def test_foreign_native_passthrough(self):
        # "read" is native to OpenCode, not Claude → passthrough.
        assert translate_tool("read", CLAUDE_TOOLS) == "read"
