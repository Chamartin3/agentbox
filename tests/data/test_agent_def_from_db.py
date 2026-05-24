"""Tests for AgentDef.from_db_row() — config_json vs content_snapshot precedence."""

from __future__ import annotations

import json
from typing import Any

import pytest
from agentbox.core.data import AgentDef


def _minimal_agent_dict(id: str = "test-agent", **extras: Any) -> dict:
    """Build a minimal AgentDef payload."""
    payload = {
        "id": id,
        "description": "Test agent",
    }
    payload.update(extras)
    return payload


class TestAgentDefFromDbRow:
    def test_prefers_config_json_over_content_snapshot(self) -> None:
        """When both columns are set, config_json takes precedence."""
        config_json_payload = _minimal_agent_dict(
            id="from-config-json",
            description="Config JSON version",
        )
        content_snapshot_payload = _minimal_agent_dict(
            id="from-snapshot",
            description="Content snapshot version",
        )

        row = {
            "config_json": json.dumps(config_json_payload),
            "content_snapshot": json.dumps(content_snapshot_payload),
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "from-config-json"
        assert result.description == "Config JSON version"

    def test_falls_back_to_content_snapshot(self) -> None:
        """When config_json is None or empty, content_snapshot is used."""
        content_snapshot_payload = _minimal_agent_dict(
            id="snapshot-agent",
            description="From snapshot",
        )

        row = {
            "config_json": None,
            "content_snapshot": json.dumps(content_snapshot_payload),
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "snapshot-agent"
        assert result.description == "From snapshot"

    def test_falls_back_to_content_snapshot_when_config_json_empty_string(
        self,
    ) -> None:
        """Empty string config_json also falls back to content_snapshot."""
        content_snapshot_payload = _minimal_agent_dict(
            id="fallback-agent",
            description="Fallback works",
        )

        row = {
            "config_json": "",
            "content_snapshot": json.dumps(content_snapshot_payload),
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "fallback-agent"
        assert result.description == "Fallback works"

    def test_raises_when_both_missing(self) -> None:
        """Both columns None/empty raises ValueError."""
        row = {
            "config_json": None,
            "content_snapshot": None,
        }

        with pytest.raises(
            ValueError, match="agent_versions row has no config payload"
        ):
            AgentDef.from_db_row(row)

    def test_handles_json_string_config_json(self) -> None:
        """config_json as JSON string (not dict) is parsed."""
        payload = _minimal_agent_dict(id="string-json-agent")
        row = {
            "config_json": json.dumps(payload),
            "content_snapshot": None,
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "string-json-agent"

    def test_handles_dict_config_json(self) -> None:
        """config_json as already-parsed dict is accepted."""
        payload = _minimal_agent_dict(id="dict-agent")
        row = {
            "config_json": payload,  # Already a dict, not JSON string
            "content_snapshot": None,
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "dict-agent"

    def test_handles_json_string_content_snapshot(self) -> None:
        """content_snapshot as JSON string (not dict) is parsed."""
        payload = _minimal_agent_dict(id="snapshot-string-agent")
        row = {
            "config_json": None,
            "content_snapshot": json.dumps(payload),
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "snapshot-string-agent"

    def test_handles_dict_content_snapshot(self) -> None:
        """content_snapshot as already-parsed dict is accepted."""
        payload = _minimal_agent_dict(id="snapshot-dict-agent")
        row = {
            "config_json": None,
            "content_snapshot": payload,  # Already a dict
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "snapshot-dict-agent"

    def test_config_json_dict_takes_precedence_over_snapshot_string(self) -> None:
        """config_json dict precedence even when content_snapshot is JSON string."""
        config_payload = _minimal_agent_dict(id="config-dict")
        snapshot_payload = _minimal_agent_dict(id="snapshot-string")

        row = {
            "config_json": config_payload,  # Dict
            "content_snapshot": json.dumps(snapshot_payload),  # String
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "config-dict"

    def test_validates_agentdef_fields(self) -> None:
        """Reconstructed AgentDef has valid fields."""
        payload = _minimal_agent_dict(
            id="validated-agent",
            description="Valid description",
            tags=["tag1", "tag2"],
        )

        row = {
            "config_json": json.dumps(payload),
            "content_snapshot": None,
        }

        result = AgentDef.from_db_row(row)
        assert result.id == "validated-agent"
        assert result.description == "Valid description"
        assert result.tags == ["tag1", "tag2"]

    def test_missing_both_keys_from_dict(self) -> None:
        """Row with neither config_json nor content_snapshot key raises."""
        row: dict[str, Any] = {}

        with pytest.raises(
            ValueError, match="agent_versions row has no config payload"
        ):
            AgentDef.from_db_row(row)
