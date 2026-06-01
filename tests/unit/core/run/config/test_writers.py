"""Unit tests for the ``ConfigWriter`` Protocol contract.

Pins the win Phase B is meant to enable: a third backend is a new
``ConfigWriter`` class plus passing it into ``ConfigGenerator``'s
``writers=`` constructor arg. No ``ConfigGenerator`` edits required.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest
from agentbox.core.run.config.discovery import DiscoveredAgent
from agentbox.core.run.config.generator import ConfigGenerator
from agentbox.core.run.config.writers import (
    DEFAULT_WRITERS,
    ConfigWriter,
    WriteContext,
    WriteResult,
)


@dataclass
class _StubAgentDiscovery:
    """Stand-in for ``AgentDiscovery`` so the unit test doesn't read disk."""

    claude_mcp_prefix: ClassVar[str] = "mcp__agentbox__"

    def discover_mcp_agents(self) -> list[DiscoveredAgent]:
        return []


class _RecordingWriter:
    """Writes a single empty file under ``target_dir``; records the call."""

    key: ClassVar[str] = "stub"
    filename: ClassVar[str] = "stub.json"

    def __init__(self) -> None:
        self.calls: list[tuple[Path, list[DiscoveredAgent], WriteContext]] = []

    def write(
        self,
        target_dir: Path,
        agents: list[DiscoveredAgent],
        ctx: WriteContext,
    ) -> WriteResult:
        path = target_dir / self.filename
        path.write_text("{}\n", encoding="utf-8")
        self.calls.append((target_dir, agents, ctx))
        return WriteResult(key=self.key, path=path, summary=None)


def _make_generator(
    *, writers: tuple[ConfigWriter, ...] | None = None
) -> ConfigGenerator:
    """Construct a ConfigGenerator that uses the stub discovery."""
    gen = ConfigGenerator(
        agentbox_toml=Path("/nonexistent.toml"),
        verbose=False,
        writers=writers,
    )
    gen.discovery = _StubAgentDiscovery()  # type: ignore[assignment]
    return gen


def test_default_writers_cover_all_four_canonical_keys() -> None:
    # Arrange
    expected_keys = {"claude_agents", "claude_settings", "claude_mcp", "opencode"}

    # Act
    actual_keys = {w.key for w in DEFAULT_WRITERS}

    # Assert
    assert actual_keys == expected_keys


def test_generate_configs_into_uses_default_writer_set(tmp_path: Path) -> None:
    # Arrange
    gen = _make_generator()

    # Act
    paths = gen.generate_configs_into(tmp_path)

    # Assert — every default writer produced its file in target_dir.
    assert set(paths.keys()) == {
        "claude_agents",
        "claude_settings",
        "claude_mcp",
        "opencode",
    }
    for key, path in paths.items():
        assert path.is_file(), f"{key} writer did not produce {path}"


def test_custom_writer_injection_runs_only_that_writer(tmp_path: Path) -> None:
    # Arrange — replace the writer set with a single recording stub.
    stub = _RecordingWriter()
    gen = _make_generator(writers=(stub,))

    # Act
    paths = gen.generate_configs_into(tmp_path)

    # Assert — only the stub wrote a file, and only its key shows up.
    assert paths == {stub.key: tmp_path / stub.filename}
    assert len(stub.calls) == 1
    called_target_dir, called_agents, called_ctx = stub.calls[0]
    assert called_target_dir == tmp_path
    assert called_agents == []
    assert isinstance(called_ctx, WriteContext)


def test_extending_default_writers_appends_without_displacement(
    tmp_path: Path,
) -> None:
    # Arrange — keep the default set, add one extra.
    stub = _RecordingWriter()
    gen = _make_generator(writers=(*DEFAULT_WRITERS, stub))

    # Act
    paths = gen.generate_configs_into(tmp_path)

    # Assert — all five files exist; the stub got its call.
    assert set(paths.keys()) == {
        "claude_agents",
        "claude_settings",
        "claude_mcp",
        "opencode",
        "stub",
    }
    assert len(stub.calls) == 1


def test_write_context_carries_constructor_kwargs(tmp_path: Path) -> None:
    # Arrange — exercise the mcp_url / servers / mcp_command pass-through.
    stub = _RecordingWriter()
    gen = ConfigGenerator(
        agentbox_toml=Path("/nonexistent.toml"),
        mcp_server_name="remote-mcp",
        mcp_command=["mcp_remote.sh", "--port", "9001"],
        mcp_url="https://mcp.example.test",
        mcp_transport="sse",
        verbose=False,
        writers=(stub,),
    )
    gen.discovery = _StubAgentDiscovery()  # type: ignore[assignment]

    # Act
    gen.generate_configs_into(tmp_path)

    # Assert — the WriteContext the stub received mirrors the constructor.
    _, _, ctx = stub.calls[0]
    assert ctx.mcp_server_name == "remote-mcp"
    assert ctx.mcp_command == ["mcp_remote.sh", "--port", "9001"]
    assert ctx.mcp_url == "https://mcp.example.test"
    assert ctx.mcp_transport == "sse"
    assert ctx.claude_mcp_prefix == "mcp__agentbox__"


@pytest.mark.parametrize(
    "field",
    [
        "allowed_builtin",
        "mcp_server_name",
        "mcp_command",
        "mcp_url",
        "mcp_transport",
        "servers",
        "claude_mcp_prefix",
    ],
)
def test_write_context_exposes_all_declared_fields(field: str) -> None:
    # Arrange / Act
    ctx = WriteContext(
        allowed_builtin=None,
        mcp_server_name="mcp",
        mcp_command=["mcp_serve.sh"],
        mcp_url=None,
        mcp_transport="http",
        servers=None,
        claude_mcp_prefix="mcp__agentbox__",
    )

    # Assert — pin the contract so adding a field is a deliberate change.
    assert hasattr(ctx, field)
