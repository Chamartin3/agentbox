"""Workspace permissions inlined into agentbox.toml (Plan 05).

Tests that WorkspaceDef correctly parses and applies permission fields
from the manifest, and that defaults are applied when fields are omitted.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.data.manifest import ProjectManifest, WorkspaceDef, WorkspaceFile


def test_workspace_def_defaults() -> None:
    """WorkspaceDef applies sensible defaults for permission fields."""
    ws = WorkspaceDef(
        name="test",
        path="workdir/test",
    )
    assert ws.allowed_tools == []
    assert ws.allowed_builtin_tools == []
    assert ws.files == []
    assert ws.max_tokens is None
    assert ws.allow_file_write is True
    assert ws.allow_network is True


def test_workspace_def_with_permissions() -> None:
    """WorkspaceDef parses permission fields from manifest."""
    ws = WorkspaceDef(
        name="restricted",
        path="workdir/restricted",
        allowed_tools=["Read", "Write"],
        allowed_builtin_tools=["bash", "python"],
        max_tokens=16000,
        allow_file_write=False,
        allow_network=False,
    )
    assert ws.allowed_tools == ["Read", "Write"]
    assert ws.allowed_builtin_tools == ["bash", "python"]
    assert ws.max_tokens == 16000
    assert ws.allow_file_write is False
    assert ws.allow_network is False


def test_workspace_file_model() -> None:
    """WorkspaceFile parses src/dst mappings."""
    f = WorkspaceFile(src="docs/readme.txt", dst="README.txt")
    assert f.src == "docs/readme.txt"
    assert f.dst == "README.txt"


def test_workspace_def_with_files() -> None:
    """WorkspaceDef parses files array."""
    ws = WorkspaceDef(
        name="with_files",
        path="workdir/with_files",
        files=[
            WorkspaceFile(src="data/config.json", dst="config.json"),
            WorkspaceFile(src="docs/guide.md", dst="guide.md"),
        ],
    )
    assert len(ws.files) == 2
    assert ws.files[0].src == "data/config.json"
    assert ws.files[0].dst == "config.json"


def test_manifest_parses_workspace_permissions(tmp_path: Path) -> None:
    """ProjectManifest parses inlined workspace permissions."""
    manifest_text = """
[[workspaces]]
name = "default"
path = "workdir/default"
allowed_tools = ["Read", "Write", "Bash"]
allowed_builtin_tools = ["python"]
max_tokens = 32000
allow_file_write = true
allow_network = true
files = [
  { src = "data/config.json", dst = "config.json" }
]

[[workspaces]]
name = "restricted"
path = "workdir/restricted"
allowed_tools = []
allowed_builtin_tools = []
max_tokens = 8000
allow_file_write = false
allow_network = false
"""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    import tomlkit

    data = tomlkit.parse(manifest_text)
    manifest = ProjectManifest.model_validate(data)

    assert len(manifest.workspaces) == 2

    default_ws = manifest.workspaces[0]
    assert default_ws.name == "default"
    assert default_ws.allowed_tools == ["Read", "Write", "Bash"]
    assert default_ws.allowed_builtin_tools == ["python"]
    assert default_ws.max_tokens == 32000
    assert default_ws.allow_file_write is True
    assert default_ws.allow_network is True
    assert len(default_ws.files) == 1
    assert default_ws.files[0].src == "data/config.json"
    assert default_ws.files[0].dst == "config.json"

    restricted_ws = manifest.workspaces[1]
    assert restricted_ws.name == "restricted"
    assert restricted_ws.allowed_tools == []
    assert restricted_ws.allowed_builtin_tools == []
    assert restricted_ws.max_tokens == 8000
    assert restricted_ws.allow_file_write is False
    assert restricted_ws.allow_network is False

    # Files are optional
    assert len(restricted_ws.files) == 0


def test_workspace_permissions_to_dict() -> None:
    """WorkspaceDef permissions can be converted to dict for config generation."""
    ws = WorkspaceDef(
        name="test",
        path="workdir/test",
        allowed_tools=["Read"],
        allowed_builtin_tools=["bash"],
        max_tokens=16000,
        allow_file_write=False,
        files=[WorkspaceFile(src="data.json", dst="data.json")],
    )

    perms_dict = {
        "allowed_tools": ws.allowed_tools,
        "allowed_builtin_tools": ws.allowed_builtin_tools,
        "files": [f.model_dump() for f in ws.files],
        "max_tokens": ws.max_tokens,
        "allow_file_write": ws.allow_file_write,
        "allow_network": ws.allow_network,
    }

    assert perms_dict["allowed_tools"] == ["Read"]
    assert perms_dict["allowed_builtin_tools"] == ["bash"]
    assert perms_dict["max_tokens"] == 16000
    assert perms_dict["allow_file_write"] is False
    assert len(perms_dict["files"]) == 1
    assert perms_dict["files"][0]["src"] == "data.json"
