"""Tests for the canonical tool-name translation hub (Plan 052)."""

from __future__ import annotations

from agentbox.core.tools.translation import canonicalize, translate_tool
from agentbox.core.workspaces.generation.engine_config.constants import (
    CLAUDE_MCP_PREFIX,
    OPENCODE_MCP_PREFIX,
)


class TestCanonicalize:
    def test_canonical_name_returns_itself(self):
        assert canonicalize("fs.read") == "fs.read"

    def test_claude_native_returns_canonical(self):
        assert canonicalize("Read") == "fs.read"
        assert canonicalize("Bash") == "shell.exec"

    def test_opencode_native_returns_canonical(self):
        assert canonicalize("read_file") == "fs.read"
        assert canonicalize("run_command") == "shell.exec"

    def test_unknown_returns_none(self):
        assert canonicalize("no.such.tool") is None

    def test_claude_mcp_name_is_none(self):
        assert canonicalize("mcp__mcp__foo") is None


class TestTranslateTool:
    # --- Claude ↔ OpenCode round-trips ---

    def test_canonical_to_opencode(self):
        assert translate_tool("fs.read", "opencode") == "read_file"

    def test_canonical_to_claude(self):
        assert translate_tool("fs.read", "claude_code") == "Read"

    def test_claude_native_to_opencode(self):
        assert translate_tool("Read", "opencode") == "read_file"
        assert translate_tool("Bash", "opencode") == "run_command"

    def test_opencode_native_to_claude(self):
        assert translate_tool("read_file", "claude_code") == "Read"
        assert translate_tool("run_command", "claude_code") == "Bash"

    # --- MCP-prefix rewrite ---

    def test_mcp_prefix_rewrite_to_opencode(self):
        assert (
            translate_tool(
                f"{CLAUDE_MCP_PREFIX}Read",
                "opencode",
                mcp_prefixes={CLAUDE_MCP_PREFIX: OPENCODE_MCP_PREFIX},
            )
            == f"{OPENCODE_MCP_PREFIX}Read"
        )

    def test_mcp_prefix_rewrite_to_claude(self):
        assert (
            translate_tool(
                f"{OPENCODE_MCP_PREFIX}read_file",
                "claude_code",
                mcp_prefixes={OPENCODE_MCP_PREFIX: CLAUDE_MCP_PREFIX},
            )
            == f"{CLAUDE_MCP_PREFIX}read_file"
        )

    # --- Unknown passthrough ---

    def test_unknown_passthrough(self):
        assert translate_tool("custom.tool", "opencode") == "custom.tool"

    def test_unknown_backend_passthrough(self):
        # Unknown backend behaves like no mapping exists.
        assert translate_tool("fs.read", "no_such_backend") == "fs.read"

    # --- Gap coverage: canonical with no target native mapping ---

    def test_gap_coverage_opencode(self):
        # "web.search" has a Claude native mapping but no OpenCode mapping.
        result = translate_tool(
            "web.search",
            "opencode",
            mcp_prefixes={CLAUDE_MCP_PREFIX: OPENCODE_MCP_PREFIX},
        )
        assert result == f"{OPENCODE_MCP_PREFIX}web.search"

    def test_gap_coverage_claude(self):
        # "todo.read" has an OpenCode native mapping but no Claude mapping.
        result = translate_tool(
            "todo.read",
            "claude_code",
            mcp_prefixes={OPENCODE_MCP_PREFIX: CLAUDE_MCP_PREFIX},
        )
        assert result == f"{CLAUDE_MCP_PREFIX}todo.read"

    def test_gap_coverage_no_prefixes_passthrough(self):
        # Without prefixes we cannot construct an env-MCP name.
        assert translate_tool("web.search", "opencode") == "web.search"

    # --- Idempotency: a name already in the target vocabulary ---

    def test_claude_mcp_name_passthrough(self):
        # Without prefixes, a Claude-native MCP name passes through unchanged.
        name = f"{CLAUDE_MCP_PREFIX}foo"
        assert translate_tool(name, "claude_code") == name

    # --- Resolution order: native name beats prefix rewrite ---

    def test_native_name_resolved_before_prefix_rewrite(self):
        # "Read" is native to Claude; even if we supply prefixes it should
        # translate to the OpenCode native "read_file", not "mcp_Read".
        assert (
            translate_tool(
                "Read",
                "opencode",
                mcp_prefixes={CLAUDE_MCP_PREFIX: OPENCODE_MCP_PREFIX},
            )
            == "read_file"
        )
