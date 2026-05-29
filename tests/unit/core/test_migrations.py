"""Tests for workspace permissions migration from capabilities.json to manifest.

Tests the migrate_capabilities_to_manifest function that migrates
workspace permissions from per-workspace JSON files to inlined manifest blocks.
"""

from __future__ import annotations

import json
from pathlib import Path

import tomlkit
from agentbox.core.migrations import migrate_capabilities_to_manifest


def test_migrate_no_manifest(tmp_path: Path) -> None:
    """Migration gracefully handles missing manifest."""
    results = migrate_capabilities_to_manifest(tmp_path)
    assert results == {}


def test_migrate_no_workspaces(tmp_path: Path) -> None:
    """Migration returns empty dict when no workspaces are defined."""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text("# empty manifest\n")

    results = migrate_capabilities_to_manifest(tmp_path)
    assert results == {}


def test_migrate_single_workspace(tmp_path: Path) -> None:
    """Migration patches a single workspace's permissions into the manifest."""
    # Create manifest with one workspace
    manifest_text = """
[[workspaces]]
name = "default"
path = "workdir/default"
description = "Default workspace"
"""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    # Create capabilities.json for this workspace
    ws_dir = tmp_path / "workdir" / "default"
    ws_dir.mkdir(parents=True)
    cap_dir = ws_dir / "permissions"
    cap_dir.mkdir()
    cap_file = cap_dir / "capabilities.json"
    cap_file.write_text(
        json.dumps(
            {
                "allowed_tools": ["Read", "Write"],
                "allowed_builtin_tools": ["bash"],
                "max_tokens": 16000,
                "allow_file_write": True,
                "allow_network": False,
            }
        )
    )

    # Run migration
    results = migrate_capabilities_to_manifest(tmp_path)

    # Check results
    assert "default" in results
    assert results["default"]["migrated"] is True
    assert results["default"]["backed_up"] is True

    # Verify backup was created
    cap_dir / "capabilities.json.migrated-20250520_000000"
    # We can't predict the exact timestamp, so just check a file matching the pattern exists
    backup_files = list(cap_dir.glob("capabilities.json.migrated-*"))
    assert len(backup_files) == 1

    # Verify manifest was updated
    updated_manifest = tomlkit.parse(manifest_path.read_text())
    updated_ws = updated_manifest["workspaces"][0]
    assert updated_ws["allowed_tools"] == ["Read", "Write"]
    assert updated_ws["allowed_builtin_tools"] == ["bash"]
    assert updated_ws["max_tokens"] == 16000
    assert updated_ws["allow_file_write"] is True
    assert updated_ws["allow_network"] is False


def test_migrate_multiple_workspaces(tmp_path: Path) -> None:
    """Migration handles multiple workspaces correctly."""
    # Create manifest with two workspaces
    manifest_text = """
[[workspaces]]
name = "default"
path = "workdir/default"

[[workspaces]]
name = "restricted"
path = "workdir/restricted"
"""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    # Create capabilities for both
    for ws_name, allowed_tools in [
        ("default", ["Read", "Write"]),
        ("restricted", []),
    ]:
        ws_dir = tmp_path / "workdir" / ws_name
        ws_dir.mkdir(parents=True)
        cap_file = ws_dir / "permissions" / "capabilities.json"
        cap_file.parent.mkdir()
        cap_file.write_text(json.dumps({"allowed_tools": allowed_tools}))

    # Run migration
    results = migrate_capabilities_to_manifest(tmp_path)

    # Check results
    assert len(results) == 2
    assert results["default"]["migrated"] is True
    assert results["restricted"]["migrated"] is True

    # Verify manifest
    updated_manifest = tomlkit.parse(manifest_path.read_text())
    default_ws = updated_manifest["workspaces"][0]
    restricted_ws = updated_manifest["workspaces"][1]

    assert default_ws["allowed_tools"] == ["Read", "Write"]
    assert restricted_ws["allowed_tools"] == []


def test_migrate_skips_missing_capabilities(tmp_path: Path) -> None:
    """Migration skips workspaces without capabilities.json."""
    # Create manifest with two workspaces
    manifest_text = """
[[workspaces]]
name = "default"
path = "workdir/default"

[[workspaces]]
name = "empty"
path = "workdir/empty"
"""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    # Create capabilities for only the first one
    ws_dir = tmp_path / "workdir" / "default"
    ws_dir.mkdir(parents=True)
    cap_file = ws_dir / "permissions" / "capabilities.json"
    cap_file.parent.mkdir()
    cap_file.write_text(json.dumps({"allowed_tools": ["Read"]}))

    # Run migration
    results = migrate_capabilities_to_manifest(tmp_path)

    # Check results - only default should be migrated
    assert results["default"]["migrated"] is True
    assert "empty" in results  # But empty is still in the results
    assert results["empty"]["migrated"] is False

    # Verify manifest - only default should have allowed_tools
    updated_manifest = tomlkit.parse(manifest_path.read_text())
    default_ws = updated_manifest["workspaces"][0]
    empty_ws = updated_manifest["workspaces"][1]

    assert "allowed_tools" in default_ws
    assert "allowed_tools" not in empty_ws


def test_migrate_idempotent(tmp_path: Path) -> None:
    """Migration is idempotent - running twice produces the same result."""
    # Create manifest with workspace
    manifest_text = """
[[workspaces]]
name = "default"
path = "workdir/default"
"""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    # Create capabilities
    ws_dir = tmp_path / "workdir" / "default"
    ws_dir.mkdir(parents=True)
    cap_file = ws_dir / "permissions" / "capabilities.json"
    cap_file.parent.mkdir()
    cap_file.write_text(json.dumps({"allowed_tools": ["Read"]}))

    # Run migration twice
    results1 = migrate_capabilities_to_manifest(tmp_path)
    manifest_after_first = manifest_path.read_text()

    results2 = migrate_capabilities_to_manifest(tmp_path)
    manifest_after_second = manifest_path.read_text()

    # Results should be consistent
    assert results1["default"]["migrated"] is True
    assert results2["default"]["migrated"] is True

    # Manifest should be unchanged on second run
    assert manifest_after_first == manifest_after_second


def test_migrate_preserves_other_fields(tmp_path: Path) -> None:
    """Migration preserves existing workspace fields in the manifest."""
    # Create manifest with other fields
    manifest_text = """
[[workspaces]]
name = "default"
path = "workdir/default"
description = "My workspace"
skills = ["python", "bash"]
"""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    # Create capabilities
    ws_dir = tmp_path / "workdir" / "default"
    ws_dir.mkdir(parents=True)
    cap_file = ws_dir / "permissions" / "capabilities.json"
    cap_file.parent.mkdir()
    cap_file.write_text(json.dumps({"allowed_tools": ["Read"]}))

    # Run migration
    migrate_capabilities_to_manifest(tmp_path)

    # Verify existing fields are preserved
    updated_manifest = tomlkit.parse(manifest_path.read_text())
    ws = updated_manifest["workspaces"][0]

    assert ws["name"] == "default"
    assert ws["path"] == "workdir/default"
    assert ws["description"] == "My workspace"
    assert ws["skills"] == ["python", "bash"]
    assert ws["allowed_tools"] == ["Read"]


def test_migrate_with_files(tmp_path: Path) -> None:
    """Migration handles files array in capabilities.json."""
    # Create manifest
    manifest_text = """
[[workspaces]]
name = "default"
path = "workdir/default"
"""
    manifest_path = tmp_path / "agentbox.toml"
    manifest_path.write_text(manifest_text)

    # Create capabilities with files
    ws_dir = tmp_path / "workdir" / "default"
    ws_dir.mkdir(parents=True)
    cap_file = ws_dir / "permissions" / "capabilities.json"
    cap_file.parent.mkdir()
    cap_file.write_text(
        json.dumps(
            {
                "allowed_tools": ["Read"],
                "files": [
                    {"src": "data/config.json", "dst": "config.json"},
                    {"src": "docs/guide.md", "dst": "guide.md"},
                ],
            }
        )
    )

    # Run migration
    migrate_capabilities_to_manifest(tmp_path)

    # Verify files were migrated
    updated_manifest = tomlkit.parse(manifest_path.read_text())
    ws = updated_manifest["workspaces"][0]

    assert "files" in ws
    assert len(ws["files"]) == 2
    assert ws["files"][0]["src"] == "data/config.json"
    assert ws["files"][0]["dst"] == "config.json"
