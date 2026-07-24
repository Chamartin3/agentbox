"""Unit tests for codex native MCP config serialization (Plans 162 / 162_02)."""

from __future__ import annotations

from agentbox.core.engines.backends.codex.mcp import (
    _toml_array,
    _toml_string,
    build_codex_intrinsic_mcp_argv,
    build_codex_mcp_argv,
    mcp_flags_from_agent_meta,
)


# ---------------------------------------------------------------------------
# TOML encoding helpers
# ---------------------------------------------------------------------------


def test_toml_string_plain() -> None:
    assert _toml_string("hello") == '"hello"'


def test_toml_string_escapes_backslash() -> None:
    assert _toml_string("a\\b") == '"a\\\\b"'


def test_toml_string_escapes_double_quote() -> None:
    assert _toml_string('say "hi"') == '"say \\"hi\\""'


def test_toml_string_escapes_newline() -> None:
    assert _toml_string("line1\nline2") == '"line1\\nline2"'


def test_toml_array_empty() -> None:
    assert _toml_array([]) == "[]"


def test_toml_array_single() -> None:
    assert _toml_array(["abc"]) == '["abc"]'


def test_toml_array_multiple() -> None:
    result = _toml_array(["a", "b c", "d"])
    assert result == '["a", "b c", "d"]'


# ---------------------------------------------------------------------------
# build_codex_mcp_argv — stdio server
# ---------------------------------------------------------------------------


def test_stdio_server_produces_command_and_args() -> None:
    servers = [
        {
            "name": "time",
            "config": {"command": ["python3", "-m", "mcp_server_time"]},
            "disabled_tools": [],
        }
    ]
    flags = build_codex_mcp_argv(servers)
    # Should produce: ["-c", "mcp_servers.time.command=...", "-c", "mcp_servers.time.args=..."]
    assert "-c" in flags
    cmd_flag_idx = flags.index("-c")
    assert flags[cmd_flag_idx + 1].startswith("mcp_servers.time.command=")
    assert '"python3"' in flags[cmd_flag_idx + 1]

    # Also has args flag
    assert any("mcp_servers.time.args=" in f for f in flags)
    args_flag = next(f for f in flags if "mcp_servers.time.args=" in f)
    assert '"mcp_server_time"' in args_flag


def test_stdio_server_omits_args_flag_when_no_args() -> None:
    """Single-element command with no args should not emit the args flag."""
    servers = [
        {
            "name": "bare",
            "config": {"command": ["/usr/bin/mcp-server"]},
            "disabled_tools": [],
        }
    ]
    flags = build_codex_mcp_argv(servers)
    assert not any("mcp_servers.bare.args=" in f for f in flags)
    assert any("mcp_servers.bare.command=" in f for f in flags)


# ---------------------------------------------------------------------------
# build_codex_mcp_argv — HTTP/remote server
# ---------------------------------------------------------------------------


def test_http_server_produces_url_flag() -> None:
    servers = [
        {
            "name": "clock",
            "config": {"url": "http://localhost:9000/mcp"},
            "disabled_tools": [],
        }
    ]
    flags = build_codex_mcp_argv(servers)
    assert any("mcp_servers.clock.url=" in f for f in flags)
    url_flag = next(f for f in flags if "mcp_servers.clock.url=" in f)
    assert '"http://localhost:9000/mcp"' in url_flag


def test_http_server_does_not_emit_command_flags() -> None:
    servers = [
        {
            "name": "remote",
            "config": {"url": "https://example.com/mcp"},
            "disabled_tools": [],
        }
    ]
    flags = build_codex_mcp_argv(servers)
    assert not any("mcp_servers.remote.command=" in f for f in flags)
    assert not any("mcp_servers.remote.args=" in f for f in flags)


# ---------------------------------------------------------------------------
# build_codex_mcp_argv — disabled_tools are NOT encoded (no per-server allowlist)
# ---------------------------------------------------------------------------


def test_disabled_tools_server_does_not_emit_tool_filter() -> None:
    """Codex has no per-server allow-list — disabled_tools must NOT appear in flags."""
    servers = [
        {
            "name": "time",
            "config": {"command": ["python3", "-m", "mcp_server_time"]},
            "disabled_tools": ["get_time"],
        }
    ]
    flags = build_codex_mcp_argv(servers)
    # No flag should reference tool filtering
    assert not any("tools" in f.lower() for f in flags)
    assert not any("allowed" in f.lower() for f in flags)
    assert not any("disabled" in f.lower() for f in flags)
    assert not any("exclude" in f.lower() for f in flags)


# ---------------------------------------------------------------------------
# build_codex_mcp_argv — multiple servers
# ---------------------------------------------------------------------------


def test_multiple_servers_each_get_flags() -> None:
    servers = [
        {
            "name": "time",
            "config": {"command": ["python3", "-m", "mcp_server_time"]},
            "disabled_tools": [],
        },
        {
            "name": "remote",
            "config": {"url": "https://example.com/mcp"},
            "disabled_tools": [],
        },
    ]
    flags = build_codex_mcp_argv(servers)
    assert any("mcp_servers.time.command=" in f for f in flags)
    assert any("mcp_servers.remote.url=" in f for f in flags)


# ---------------------------------------------------------------------------
# build_codex_mcp_argv — edge cases
# ---------------------------------------------------------------------------


def test_empty_server_list_returns_empty_flags() -> None:
    assert build_codex_mcp_argv([]) == []


def test_server_with_no_name_is_skipped() -> None:
    servers = [{"name": "", "config": {"url": "http://x"}, "disabled_tools": []}]
    assert build_codex_mcp_argv(servers) == []


def test_server_with_missing_config_is_skipped() -> None:
    servers = [{"name": "mystery", "config": {}, "disabled_tools": []}]
    assert build_codex_mcp_argv(servers) == []


# ---------------------------------------------------------------------------
# mcp_flags_from_agent_meta — integration entry point
# ---------------------------------------------------------------------------


def test_mcp_flags_from_agent_meta_reads_external_servers() -> None:
    agent_meta = {
        "external_mcp_servers": [
            {
                "name": "time",
                "config": {"command": ["python3", "-m", "mcp_server_time"]},
                "disabled_tools": [],
            }
        ]
    }
    flags = mcp_flags_from_agent_meta(agent_meta)
    assert any("mcp_servers.time.command=" in f for f in flags)


def test_mcp_flags_from_agent_meta_empty_when_no_servers() -> None:
    assert mcp_flags_from_agent_meta({}) == []
    assert mcp_flags_from_agent_meta({"external_mcp_servers": None}) == []
    assert mcp_flags_from_agent_meta({"external_mcp_servers": []}) == []


def test_mcp_flags_from_agent_meta_multiple_servers() -> None:
    agent_meta = {
        "external_mcp_servers": [
            {
                "name": "srv1",
                "config": {"url": "http://host1/mcp"},
                "disabled_tools": [],
            },
            {
                "name": "srv2",
                "config": {"url": "http://host2/mcp"},
                "disabled_tools": [],
            },
        ]
    }
    flags = mcp_flags_from_agent_meta(agent_meta)
    assert any("mcp_servers.srv1.url=" in f for f in flags)
    assert any("mcp_servers.srv2.url=" in f for f in flags)


# ---------------------------------------------------------------------------
# build_codex_intrinsic_mcp_argv — intrinsic server re-resolution (Plan 162_02)
# ---------------------------------------------------------------------------


def test_intrinsic_mcp_argv_host_env_server() -> None:
    """A host-env spec with command + args produces the expected -c flags."""
    import sys

    specs = {
        "agentbox-host-env": {
            "command": sys.executable,
            "args": ["-m", "agentbox.core.tools.mcp_servers.host_env"],
            "env": {
                "AGENTBOX_HOST_ENV_GRANTS_JSON": '{"fs.read": {}}',
                "AGENTBOX_HOST_ENV_WORKSPACE_ID": "ws-1",
                "AGENTBOX_HOST_ENV_WORKDIR": "/data/workdir",
                "AGENTBOX_DB_PATH": "/data/agentbox.sqlite",
            },
        }
    }
    flags = build_codex_intrinsic_mcp_argv(specs)

    # Must emit a command flag
    assert any("mcp_servers.agentbox-host-env.command=" in f for f in flags)
    cmd_flag = next(f for f in flags if "mcp_servers.agentbox-host-env.command=" in f)
    assert f'"{sys.executable}"' in cmd_flag

    # Must emit an args flag containing the module name
    assert any("mcp_servers.agentbox-host-env.args=" in f for f in flags)
    args_flag = next(f for f in flags if "mcp_servers.agentbox-host-env.args=" in f)
    assert '"agentbox.core.tools.mcp_servers.host_env"' in args_flag


def test_intrinsic_mcp_argv_env_is_not_emitted_as_toml() -> None:
    """The env block is NOT encoded into TOML flags (goes into subprocess env instead)."""
    specs = {
        "agentbox-host-env": {
            "command": "/usr/bin/python3",
            "args": ["-m", "some.server"],
            "env": {"SECRET_KEY": "secret_value"},
        }
    }
    flags = build_codex_intrinsic_mcp_argv(specs)

    # No flag should contain env var names or values
    assert not any("SECRET_KEY" in f for f in flags)
    assert not any("secret_value" in f for f in flags)


def test_intrinsic_mcp_argv_no_args_omits_args_flag() -> None:
    """A spec with empty args list does not emit an args -c flag."""
    specs = {
        "agentbox-agent-tools": {
            "command": "/usr/bin/python3",
            "args": [],
            "env": {},
        }
    }
    flags = build_codex_intrinsic_mcp_argv(specs)

    assert any("mcp_servers.agentbox-agent-tools.command=" in f for f in flags)
    assert not any("mcp_servers.agentbox-agent-tools.args=" in f for f in flags)


def test_intrinsic_mcp_argv_multiple_servers() -> None:
    """Multiple intrinsic servers each produce their own -c flags."""
    specs = {
        "agentbox-host-env": {
            "command": "/usr/bin/python3",
            "args": ["-m", "host_env"],
            "env": {},
        },
        "agentbox-agent-tools": {
            "command": "/usr/bin/python3",
            "args": ["-m", "agent_tools"],
            "env": {},
        },
    }
    flags = build_codex_intrinsic_mcp_argv(specs)

    assert any("mcp_servers.agentbox-host-env.command=" in f for f in flags)
    assert any("mcp_servers.agentbox-host-env.args=" in f for f in flags)
    assert any("mcp_servers.agentbox-agent-tools.command=" in f for f in flags)
    assert any("mcp_servers.agentbox-agent-tools.args=" in f for f in flags)


def test_intrinsic_mcp_argv_empty_input_returns_empty() -> None:
    """Empty spec dict returns empty flags list."""
    assert build_codex_intrinsic_mcp_argv({}) == []


def test_intrinsic_mcp_argv_spec_without_command_is_skipped() -> None:
    """A spec with no command key is skipped gracefully."""
    specs = {
        "agentbox-host-env": {
            "command": "",  # empty → falsy
            "args": ["-m", "something"],
            "env": {},
        }
    }
    assert build_codex_intrinsic_mcp_argv(specs) == []
