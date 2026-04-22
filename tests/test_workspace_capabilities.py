"""Workspace capabilities.json is the runtime config source.

When permissions are saved via the UI, capabilities.json is written and the
generator regenerates .agentbox/generated/*. Runners later read this same
capabilities.json to pick up workspace-level config (mcp_config_path,
allowed_tools).
"""

from __future__ import annotations

import json
from pathlib import Path

from agentbox.core.workspaces import (
    capabilities_path,
    load_capabilities,
)


def test_load_returns_empty_when_missing(tmp_path: Path) -> None:
    assert load_capabilities(tmp_path) == {}


def test_load_returns_parsed_json(tmp_path: Path) -> None:
    cap = capabilities_path(tmp_path)
    cap.parent.mkdir(parents=True)
    cap.write_text(
        json.dumps(
            {
                "allowed_tools": ["Read", "Grep"],
                "mcp_config_path": "bin/claude/mcp.json",
                "max_tokens": 32000,
            }
        )
    )

    data = load_capabilities(tmp_path)
    assert data["allowed_tools"] == ["Read", "Grep"]
    assert data["mcp_config_path"] == "bin/claude/mcp.json"
    assert data["max_tokens"] == 32000


def test_load_returns_empty_on_corrupt_json(tmp_path: Path) -> None:
    cap = capabilities_path(tmp_path)
    cap.parent.mkdir(parents=True)
    cap.write_text("{ not json")

    # Corrupt config should not blow up the runner — fall back to defaults.
    assert load_capabilities(tmp_path) == {}


def test_capabilities_path_layout(tmp_path: Path) -> None:
    # Contract: UI writer and runner reader agree on this exact path.
    assert capabilities_path(tmp_path) == tmp_path / "permissions" / "capabilities.json"
