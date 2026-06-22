"""Regression tests for host-env tool wiring on the token direct path.

The bug these guard against: the token backend constructed its pydantic-ai
``Agent`` with no tools, so the model was never offered ``fs.read`` / ``fs.list``
and could only hallucinate file contents (0 ``tool_call`` events, every model).
These tests assert (a) the tool builder honours grants + path scoping and
(b) the backend actually passes the tools into the ``Agent`` constructor.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentbox.core.engines.backends.token import TokenBackend
from agentbox.core.engines.backends.token.tools import (
    build_host_env_tools,
    build_host_env_toolsets,
)
from agentbox.core.engines.contracts.base import RenderedConfig

FS_GRANTS = {
    "fs.read": {"allowed_paths": ["/work"], "max_bytes": 1048576},
    "fs.list": {"allowed_paths": ["/work"]},
}


# --------------------------------------------------------------- builder unit
def test_builds_both_tools_for_full_grants() -> None:
    tools = build_host_env_tools(FS_GRANTS, {"fs.read", "fs.list"})
    assert sorted(t.__name__ for t in tools) == ["fs_list", "fs_read"]


def test_no_grants_means_no_tools() -> None:
    assert build_host_env_tools(None) == []
    assert build_host_env_tools({}) == []


def test_mcp_toolsets_killswitch(monkeypatch) -> None:
    # MCP is the default tool route; AGENTBOX_TOKEN_MCP_TOOLS=0 forces the
    # in-process fallback (returns [] so no subprocess is spawned).
    monkeypatch.setenv("AGENTBOX_TOKEN_MCP_TOOLS", "0")
    assert build_host_env_toolsets(FS_GRANTS, "ws", "/work", "/db.sqlite") == []


def test_agent_grant_gates_workspace_grant() -> None:
    # Workspace allows both; agent only granted fs.list -> only fs_list built.
    tools = build_host_env_tools(FS_GRANTS, {"fs.list"})
    assert [t.__name__ for t in tools] == ["fs_list"]


def test_none_agent_grants_means_no_agent_restriction() -> None:
    tools = build_host_env_tools(FS_GRANTS, None)
    assert sorted(t.__name__ for t in tools) == ["fs_list", "fs_read"]


def test_path_scoping_enforced_before_any_io(tmp_path: Path) -> None:
    inside = tmp_path / "ok.txt"
    inside.write_text("hello", encoding="utf-8")
    grants = {
        "fs.read": {"allowed_paths": [str(tmp_path)], "max_bytes": 1048576},
        "fs.list": {"allowed_paths": [str(tmp_path)]},
    }
    fs_read = next(t for t in build_host_env_tools(grants) if t.__name__ == "fs_read")

    assert fs_read(str(inside)) == "hello"
    # An out-of-scope path is refused and never read.
    denied = fs_read("/etc/passwd")
    assert denied.startswith("ERROR:")
    assert "allowed_paths" in denied


def test_fs_list_returns_string_not_array(tmp_path: Path) -> None:
    # Regression: a list return serializes as a JSON array in the tool result,
    # which Ollama's OpenAI-compat endpoint 400s on. Must be a string.
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("y", encoding="utf-8")
    grants = {"fs.list": {"allowed_paths": [str(tmp_path)]}}
    fs_list = next(t for t in build_host_env_tools(grants) if t.__name__ == "fs_list")
    out = fs_list(str(tmp_path))
    assert isinstance(out, str)
    assert "a.md" in out and "b.txt" in out
    assert fs_list("/etc").startswith("ERROR:")


# ----------------------------------------------------------- backend wiring
async def _collect(agen):
    return [ev async for ev in agen]


def _capture_agent_tools() -> tuple[MagicMock, dict]:
    """Return a fake Agent class that records constructor kwargs."""
    captured: dict = {}

    @contextlib.asynccontextmanager
    async def _stream(*_a, **_k):
        class _Result:
            output = "done"
            usage = MagicMock(return_value=MagicMock(input_tokens=1, output_tokens=1, model="m"))
            all_messages = MagicMock(return_value=[])

        class _Evt:
            result = _Result()

        class _S:
            def __aiter__(self):
                async def _gen():
                    yield _Evt()
                return _gen()

        yield _S()

    def _fake_agent(*args, **kwargs):
        captured["kwargs"] = kwargs
        inst = MagicMock()
        inst.run_stream_events = _stream
        inst.system_prompt = lambda fn: fn

        # The MCP-toolset path enters the agent's async context; support it.
        async def _aenter(*_a):
            return inst

        async def _aexit(*_a):
            return False

        inst.__aenter__ = _aenter
        inst.__aexit__ = _aexit
        return inst

    return _fake_agent, captured


def _grant_rendered() -> RenderedConfig:
    return RenderedConfig(
        cwd=Path("."),
        agent_meta={
            "agent_module": None,
            "prompt": "sys",
            "model": "ollama:llama3.2:1b",
            "output_schema": None,
            "host_env_grants": FS_GRANTS,
            "agent_tool_grants": ["fs.read", "fs.list"],
            "host_env_workspace_id": "ws",
            "host_env_workdir": "/work",
            "host_env_db_path": "/data/agentbox.sqlite",
        },
        model="ollama:llama3.2:1b",
    )


async def test_backend_prefers_mcp_toolset_when_available() -> None:
    # When the host-env MCP toolset can be built, it's wired as `toolsets`
    # (full parity with other backends), not the in-process `tools`.
    fake_agent, captured = _capture_agent_tools()
    sentinel = [object()]
    with (
        patch("pydantic_ai.Agent", side_effect=fake_agent),
        patch(
            "agentbox.core.engines.backends.token.run_direct.build_host_env_toolsets",
            return_value=sentinel,
        ),
    ):
        events = await _collect(TokenBackend().run(_grant_rendered(), "list /work", "rid"))

    assert captured["kwargs"].get("toolsets") == sentinel
    assert "tools" not in captured["kwargs"]
    assert any(e.type == "log" and "MCP toolset" in e.message for e in events)


async def test_backend_falls_back_to_inprocess_tools() -> None:
    # When the MCP toolset is unavailable (returns []), the in-process
    # fs.read/fs.list tools are wired instead so the model still has tools.
    fake_agent, captured = _capture_agent_tools()
    with (
        patch("pydantic_ai.Agent", side_effect=fake_agent),
        patch(
            "agentbox.core.engines.backends.token.run_direct.build_host_env_toolsets",
            return_value=[],
        ),
    ):
        events = await _collect(TokenBackend().run(_grant_rendered(), "list /work", "rid"))

    tools = captured["kwargs"].get("tools")
    assert tools and sorted(t.__name__ for t in tools) == ["fs_list", "fs_read"]
    assert "toolsets" not in captured["kwargs"]
    assert any(e.type == "log" and "in-process" in e.message for e in events)


async def test_backend_wires_no_tools_without_grants() -> None:
    fake_agent, captured = _capture_agent_tools()
    rendered = RenderedConfig(
        cwd=Path("."),
        agent_meta={
            "agent_module": None,
            "prompt": "sys",
            "model": "ollama:llama3.2:1b",
            "output_schema": None,
        },
        model="ollama:llama3.2:1b",
    )
    with patch("pydantic_ai.Agent", side_effect=fake_agent):
        await _collect(TokenBackend().run(rendered, "hi", "rid"))

    assert "tools" not in captured["kwargs"]
