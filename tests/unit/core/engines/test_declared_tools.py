"""BackendAdapter.declared_tools() — each backend declares its native tools."""

from __future__ import annotations

from agentbox.core.engines.backends.claude_code.adapter import ClaudeCodeBackend
from agentbox.core.engines.backends.codex.adapter import CodexBackend
from agentbox.core.engines.backends.opencode.adapter import OpenCodeBackend
from agentbox.core.data import CanonicalTool


def test_claude_declares_native_tools() -> None:
    tools = ClaudeCodeBackend().declared_tools()
    # Claude natively provides Read/Bash → their canonical names.
    assert CanonicalTool.FS_READ in tools
    assert CanonicalTool.SHELL_EXEC in tools


def test_opencode_declares_native_tools() -> None:
    assert CanonicalTool.FS_READ in OpenCodeBackend().declared_tools()


def test_codex_declares_native_tools() -> None:
    assert CodexBackend().declared_tools()  # non-empty native set
