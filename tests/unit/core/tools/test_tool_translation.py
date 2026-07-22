"""Tests for the canonical tool-name translation hub (Plan 052, 056, 061_01)."""

from __future__ import annotations

from agentbox.core.engines.backends.claude_code.tools import (
    NATIVE_TOOLS as CLAUDE_TOOLS,
)
from agentbox.core.engines.backends.codex.tools import NATIVE_TOOLS as CODEX_TOOLS
from agentbox.core.engines.backends.opencode.tools import (
    NATIVE_TOOLS as OPENCODE_TOOLS,
)
from agentbox.core.engines.backends.pi.tools import NATIVE_TOOLS as PI_TOOLS
from agentbox.core.tools.translation import translate_tool

# MCP server name prefixes — opaque strings passed to translate_tool's
# mcp_prefixes map. (Were engine_config.constants before that legacy package
# was removed; the values are all this test needs.)
CLAUDE_MCP_PREFIX = "mcp__mcp__"
OPENCODE_MCP_PREFIX = "mcp_"


class TestTranslateTool:
    # --- Canonical → native (direct lookup) ---

    def test_canonical_to_opencode(self):
        assert translate_tool("fs.read", OPENCODE_TOOLS) == "read"
        assert translate_tool("shell.exec", OPENCODE_TOOLS) == "bash"

    def test_canonical_to_claude(self):
        assert translate_tool("fs.read", CLAUDE_TOOLS) == "Read"
        assert translate_tool("shell.exec", CLAUDE_TOOLS) == "Bash"

    # --- Native name already in target vocabulary (idempotent) ---

    def test_claude_native_idempotent(self):
        assert translate_tool("Read", CLAUDE_TOOLS) == "Read"
        assert translate_tool("Bash", CLAUDE_TOOLS) == "Bash"

    def test_opencode_native_idempotent(self):
        assert translate_tool("read", OPENCODE_TOOLS) == "read"
        assert translate_tool("bash", OPENCODE_TOOLS) == "bash"

    # --- Names native to another backend are NOT cross-translated ---

    def test_foreign_native_passthrough(self):
        # "Read" is native to Claude Code but not to OpenCode → passthrough.
        assert translate_tool("Read", OPENCODE_TOOLS) == "Read"
        assert translate_tool("Bash", OPENCODE_TOOLS) == "Bash"
        assert translate_tool("read", CLAUDE_TOOLS) == "read"
        assert translate_tool("bash", CLAUDE_TOOLS) == "bash"

    # --- MCP-prefix rewrite ---

    def test_mcp_prefix_rewrite_to_opencode(self):
        assert (
            translate_tool(
                f"{CLAUDE_MCP_PREFIX}Read",
                OPENCODE_TOOLS,
                mcp_prefixes={CLAUDE_MCP_PREFIX: OPENCODE_MCP_PREFIX},
            )
            == f"{OPENCODE_MCP_PREFIX}Read"
        )

    def test_mcp_prefix_rewrite_to_claude(self):
        assert (
            translate_tool(
                f"{OPENCODE_MCP_PREFIX}read_file",
                CLAUDE_TOOLS,
                mcp_prefixes={OPENCODE_MCP_PREFIX: CLAUDE_MCP_PREFIX},
            )
            == f"{CLAUDE_MCP_PREFIX}read_file"
        )

    # --- Unknown passthrough ---

    def test_unknown_passthrough(self):
        assert translate_tool("custom.tool", OPENCODE_TOOLS) == "custom.tool"

    # --- Gap coverage: canonical with no target native mapping ---

    def test_gap_coverage_opencode(self):
        # "web.search" is canonical but has no OpenCode mapping.
        result = translate_tool(
            "web.search",
            OPENCODE_TOOLS,
            mcp_prefixes={CLAUDE_MCP_PREFIX: OPENCODE_MCP_PREFIX},
        )
        assert result == f"{OPENCODE_MCP_PREFIX}web.search"

    def test_gap_coverage_claude(self):
        # "todo.read" is canonical but has no Claude Code mapping.
        result = translate_tool(
            "todo.read",
            CLAUDE_TOOLS,
            mcp_prefixes={OPENCODE_MCP_PREFIX: CLAUDE_MCP_PREFIX},
        )
        assert result == f"{CLAUDE_MCP_PREFIX}todo.read"

    def test_gap_coverage_no_prefixes_passthrough(self):
        # Without prefixes we cannot construct an env-MCP name.
        assert translate_tool("web.search", OPENCODE_TOOLS) == "web.search"

    # --- Idempotency: MCP-prefixed name passes through unchanged ---

    def test_claude_mcp_name_passthrough(self):
        # Without prefixes, a Claude-native MCP name passes through unchanged.
        name = f"{CLAUDE_MCP_PREFIX}foo"
        assert translate_tool(name, CLAUDE_TOOLS) == name

    # --- Resolution order: native name beats prefix rewrite ---

    def test_native_name_resolved_before_prefix_rewrite(self):
        # "Read" IS a native name in Claude Code, so we return it directly before
        # checking MCP prefixes.
        assert (
            translate_tool(
                "Read",
                CLAUDE_TOOLS,
                mcp_prefixes={CLAUDE_MCP_PREFIX: OPENCODE_MCP_PREFIX},
            )
            == "Read"
        )


# ── pi backend (Plan 056) ────────────────────────────────────────────────────


class TestPiNativeNames:
    """pi v0.75.4: built-in tools read/bash/edit/write, plus grep/find/ls."""

    def test_canonical_to_pi(self):
        assert translate_tool("fs.read", PI_TOOLS) == "read"
        assert translate_tool("shell.exec", PI_TOOLS) == "bash"
        assert translate_tool("fs.edit", PI_TOOLS) == "edit"
        assert translate_tool("fs.write", PI_TOOLS) == "write"
        assert translate_tool("fs.grep", PI_TOOLS) == "grep"
        assert translate_tool("fs.glob", PI_TOOLS) == "find"
        assert translate_tool("fs.list", PI_TOOLS) == "ls"

    def test_pi_native_idempotent(self):
        assert translate_tool("read", PI_TOOLS) == "read"
        assert translate_tool("bash", PI_TOOLS) == "bash"
        assert translate_tool("ls", PI_TOOLS) == "ls"

    def test_unsupported_tool_passthrough(self):
        # "agent.task" has no pi mapping → passthrough.
        assert translate_tool("agent.task", PI_TOOLS) == "agent.task"

    def test_claude_native_to_pi_passthrough(self):
        # "Read" is native to Claude Code, not pi → passthrough.
        assert translate_tool("Read", PI_TOOLS) == "Read"


# ── codex backend (Plan 056) ──────────────────────────────────────────────────


class TestCodexNativeNames:
    """codex: Claude Code API-compatible — mirrors PascalCase tool names."""

    def test_canonical_to_codex(self):
        assert translate_tool("fs.read", CODEX_TOOLS) == "Read"
        assert translate_tool("shell.exec", CODEX_TOOLS) == "Bash"
        assert translate_tool("fs.edit", CODEX_TOOLS) == "Edit"
        assert translate_tool("fs.write", CODEX_TOOLS) == "Write"
        assert translate_tool("fs.list", CODEX_TOOLS) == "LS"
        assert translate_tool("fs.glob", CODEX_TOOLS) == "Glob"
        assert translate_tool("fs.grep", CODEX_TOOLS) == "Grep"
        assert translate_tool("agent.task", CODEX_TOOLS) == "Task"
        assert translate_tool("interaction.ask_user", CODEX_TOOLS) == "AskUserQuestion"

    def test_codex_native_idempotent(self):
        assert translate_tool("Read", CODEX_TOOLS) == "Read"
        assert translate_tool("Bash", CODEX_TOOLS) == "Bash"
        assert translate_tool("LS", CODEX_TOOLS) == "LS"

    def test_opencode_native_to_codex_passthrough(self):
        # "read" is native to OpenCode, not codex → passthrough.
        assert translate_tool("read", CODEX_TOOLS) == "read"
