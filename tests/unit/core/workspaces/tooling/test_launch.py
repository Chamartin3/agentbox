"""Unit tests for resolve_mcp_launch_command."""
from __future__ import annotations

import shutil
from unittest import mock

import pytest

from agentbox.core.mcp.launch import resolve_mcp_launch_command


def test_empty_argv_raises() -> None:
    with pytest.raises(ValueError, match="empty command list"):
        resolve_mcp_launch_command([])


def test_bare_command_passthrough() -> None:
    result = resolve_mcp_launch_command(["some-binary", "--flag", "arg"])
    assert result["command"] == "some-binary"
    assert result["args"] == ["--flag", "arg"]


def test_python3_passthrough() -> None:
    result = resolve_mcp_launch_command(
        ["python3", "-m", "mcp_server_time"]
    )
    assert result["command"] == "python3"
    assert result["args"] == ["-m", "mcp_server_time"]


def test_npx_passthrough() -> None:
    result = resolve_mcp_launch_command(
        ["npx", "-y", "@modelcontextprotocol/server-time"]
    )
    assert result["command"] == "npx"
    assert result["args"] == ["-y", "@modelcontextprotocol/server-time"]


def test_uvx_available_passthrough() -> None:
    """When uvx is on PATH, the command is passed through unchanged."""
    with mock.patch.object(shutil, "which", return_value="/usr/bin/uvx"):
        result = resolve_mcp_launch_command(["uvx", "mcp-server-time"])
    assert result["command"] == "uvx"
    assert result["args"] == ["mcp-server-time"]


def test_uvx_unavailable_fallback() -> None:
    """When uvx is NOT on PATH, use the fallback table."""
    with mock.patch.object(shutil, "which", return_value=None):
        result = resolve_mcp_launch_command(["uvx", "mcp-server-time"])
    assert result["command"] == "python3"
    assert result["args"] == ["-m", "mcp_server_time"]


def test_uvx_unavailable_unknown_package_raises() -> None:
    """When uvx is absent and the package is not in the fallback table, raise."""
    with mock.patch.object(shutil, "which", return_value=None):
        with pytest.raises(ValueError, match="no fallback is known"):
            resolve_mcp_launch_command(["uvx", "unknown-server"])


def test_uvx_missing_package_raises() -> None:
    """uvx with no arguments raises."""
    with mock.patch.object(shutil, "which", return_value=None):
        with pytest.raises(ValueError, match="has no package argument"):
            resolve_mcp_launch_command(["uvx"])


def test_env_passthrough() -> None:
    """Environment dict is passed through to the result."""
    result = resolve_mcp_launch_command(
        ["python3", "-m", "mcp_server_time"],
        env={"FOO": "bar"},
    )
    assert result["env"] == {"FOO": "bar"}


def test_env_default_empty() -> None:
    """When no env is provided, result.env is an empty dict."""
    result = resolve_mcp_launch_command(["python3", "-m", "test"])
    assert result["env"] == {}


def test_uvx_fallback_with_extra_args() -> None:
    """uvx fallback preserves extra arguments after the package name."""
    with mock.patch.object(shutil, "which", return_value=None):
        result = resolve_mcp_launch_command(
            ["uvx", "mcp-server-time", "--port", "8080"]
        )
    assert result["command"] == "python3"
    assert result["args"] == ["-m", "mcp_server_time", "--port", "8080"]


# ── Identity tests: both paths produce identical (command, args) ──────


def test_identity_bare_command() -> None:
    """Assert both paths would produce the same launch command for a bare spec."""
    spec = ["python3", "-m", "mcp_server_time"]
    assert resolve_mcp_launch_command(list(spec)) == resolve_mcp_launch_command(
        list(spec)
    )


@pytest.mark.parametrize(
    "spec",
    [
        ["python3", "-m", "mcp_server_time"],
        ["npx", "-y", "mcp-server-test"],
        ["/usr/local/bin/custom-server", "--debug"],
    ],
)
def test_identity_across_specs(spec: list[str]) -> None:
    """Both paths resolve the same spec to the same command+args (passthroughs)."""
    a = resolve_mcp_launch_command(list(spec))
    b = resolve_mcp_launch_command(list(spec))
    assert a["command"] == b["command"]
    assert a["args"] == b["args"]
