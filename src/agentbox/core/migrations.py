"""Migration utilities for agentbox manifest and workspace configs."""

from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path

import tomlkit
from tomlkit.items import AoT, item


def migrate_capabilities_to_manifest(project_root: Path) -> dict[str, dict]:
    """Migrate workspace capabilities.json files into agentbox.toml.

    For each workspace defined in agentbox.toml:
    1. Reads <workspace>/permissions/capabilities.json if it exists.
    2. Patches the corresponding [[workspaces]] block in manifest.toml.
    3. Writes a backup at capabilities.json.migrated-<date>.

    Returns a dict mapping workspace names to dicts of {migrated: bool, backed_up: bool}.
    """
    manifest_path = project_root / "agentbox.toml"
    if not manifest_path.exists():
        return {}

    # Parse manifest
    manifest_text = manifest_path.read_text(encoding="utf-8")
    parsed = tomlkit.parse(manifest_text)

    # Get list of workspaces from the manifest
    workspaces_aot = parsed.get("workspaces", [])
    if not isinstance(workspaces_aot, AoT):
        return {}

    results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for ws_table in workspaces_aot:
        ws_name = ws_table.get("name")
        ws_path_str = ws_table.get("path")
        if not ws_name or not ws_path_str:
            continue

        ws_abs_path = project_root / ws_path_str
        capabilities_path = ws_abs_path / "permissions" / "capabilities.json"

        results[ws_name] = {"migrated": False, "backed_up": False}

        if not capabilities_path.exists():
            continue

        # Read capabilities.json
        try:
            capabilities = json.loads(capabilities_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            warnings.warn(
                f"Failed to read {capabilities_path}, skipping migration for {ws_name}",
                stacklevel=2,
            )
            continue

        # Patch the workspace table
        if "allowed_tools" in capabilities:
            ws_table["allowed_tools"] = item(capabilities["allowed_tools"])

        if "allowed_builtin_tools" in capabilities:
            ws_table["allowed_builtin_tools"] = item(
                capabilities["allowed_builtin_tools"]
            )

        if capabilities.get("max_tokens") is not None:
            ws_table["max_tokens"] = item(capabilities["max_tokens"])

        if "allow_file_write" in capabilities:
            ws_table["allow_file_write"] = item(capabilities["allow_file_write"])

        if "allow_network" in capabilities:
            ws_table["allow_network"] = item(capabilities["allow_network"])

        if capabilities.get("files"):
            files_list = []
            for file_entry in capabilities["files"]:
                if isinstance(file_entry, dict):
                    # tomlkit will handle conversion to proper format via item()
                    files_list.append(
                        {
                            "src": file_entry.get("src", ""),
                            "dst": file_entry.get("dst", ""),
                        }
                    )
            if files_list:
                ws_table["files"] = item(files_list)

        # Write backup
        backup_path = (
            capabilities_path.parent / f"capabilities.json.migrated-{timestamp}"
        )
        try:
            backup_path.write_text(capabilities_path.read_text(encoding="utf-8"))
            results[ws_name]["backed_up"] = True
        except OSError:
            warnings.warn(f"Failed to write backup to {backup_path}", stacklevel=2)

        results[ws_name]["migrated"] = True

    # Write updated manifest atomically
    if any(r["migrated"] for r in results.values()):
        new_manifest_text = tomlkit.dumps(parsed)
        tmp_path = manifest_path.with_suffix(".toml.tmp")
        tmp_path.write_text(new_manifest_text, encoding="utf-8")
        tmp_path.replace(manifest_path)

    return results
