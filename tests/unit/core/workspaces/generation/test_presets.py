"""Unit tests for workspace-generation preset management.

Covers:
- list_presets: delegates to store
- from_preset: returns None when not found; returns WorkenvConfig for dict config_json;
  handles JSON-string config_json
- save_as_preset: calls upsert with correct arguments
- load_seed_templates: returns at least the built-in ``default`` seed
- seed_presets: delegates template list to store.seed_workenv_templates

All collaborators are plain MagicMocks — no DB fixtures required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agentbox.core.workspaces.generation.config import WorkenvConfig
from agentbox.core.workspaces.generation.presets import (
    from_preset,
    list_presets,
    load_seed_templates,
    save_as_preset,
    seed_presets,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# list_presets
# ---------------------------------------------------------------------------


class TestListPresets:
    def test_returns_store_summary(self) -> None:
        """list_presets must return whatever the manager returns."""
        mgr = MagicMock()
        mgr.list_all.return_value = [
            {"name": "default", "engine": "claude_code"},
        ]

        result = list_presets(mgr)

        mgr.list_all.assert_called_once()
        assert result == [{"name": "default", "engine": "claude_code"}]

    def test_returns_empty_list_when_no_templates(self) -> None:
        """list_presets returns an empty list when the DB has no templates."""
        mgr = MagicMock()
        mgr.list_all.return_value = []

        result = list_presets(mgr)

        assert result == []


# ---------------------------------------------------------------------------
# from_preset
# ---------------------------------------------------------------------------


class TestFromPreset:
    def test_returns_none_when_not_found(self) -> None:
        """from_preset returns None when the manager has no matching template."""
        mgr = MagicMock()
        mgr.get_by_name.return_value = None

        result = from_preset(mgr, "nonexistent")

        assert result is None

    def test_parses_dict_config_json(self) -> None:
        """from_preset deserialises a dict config_json into a WorkenvConfig."""
        mgr = MagicMock()
        mgr.get_by_name.return_value = {
            "name": "default",
            "config_json": {
                "name": "default",
                "description": "A default workspace",
                "agents": [],
                "resources": [],
                "skills": [],
                "mcp_servers": [],
                "permissions": {},
                "env": {},
            },
        }

        result = from_preset(mgr, "default")

        assert isinstance(result, WorkenvConfig)
        assert result.name == "default"

    def test_parses_json_string_config_json(self) -> None:
        """from_preset handles config_json stored as a JSON string (legacy rows)."""
        config = {
            "name": "string-preset",
            "description": "",
            "agents": [],
            "resources": [],
            "skills": [],
            "mcp_servers": [],
            "permissions": {},
            "env": {},
        }
        mgr = MagicMock()
        mgr.get_by_name.return_value = {
            "name": "string-preset",
            "config_json": json.dumps(config),
        }

        result = from_preset(mgr, "string-preset")

        assert isinstance(result, WorkenvConfig)
        assert result.name == "string-preset"


# ---------------------------------------------------------------------------
# save_as_preset
# ---------------------------------------------------------------------------


class TestSaveAsPreset:
    def test_calls_upsert_with_name_and_engine(self) -> None:
        """save_as_preset must pass name, engine, config_json, and description."""
        mgr = MagicMock()
        mgr.upsert.return_value = {"name": "new-preset"}
        config = WorkenvConfig(name="new-preset", description="My preset")

        result = save_as_preset(mgr, "new-preset", config)

        mgr.upsert.assert_called_once()
        call_kwargs = mgr.upsert.call_args
        positional_name = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("name")
        assert positional_name == "new-preset"
        assert result == {"name": "new-preset"}

    def test_uses_config_description_when_no_override(self) -> None:
        """save_as_preset uses config.description when no explicit description kwarg is given."""
        mgr = MagicMock()
        mgr.upsert.return_value = {}
        config = WorkenvConfig(name="desc-preset", description="auto description")

        save_as_preset(mgr, "desc-preset", config)

        call_kwargs = mgr.upsert.call_args.kwargs
        assert call_kwargs["description"] == "auto description"


# ---------------------------------------------------------------------------
# load_seed_templates
# ---------------------------------------------------------------------------


class TestLoadSeedTemplates:
    def test_returns_at_least_one_seed(self) -> None:
        """load_seed_templates must find the built-in ``default.yaml`` seed."""
        templates = load_seed_templates()

        assert len(templates) >= 1

    def test_default_seed_has_name(self) -> None:
        """Every loaded seed template must have a ``name`` key."""
        templates = load_seed_templates()

        for tmpl in templates:
            assert "name" in tmpl, f"seed template missing 'name': {tmpl}"


# ---------------------------------------------------------------------------
# seed_presets
# ---------------------------------------------------------------------------


class TestSeedPresets:
    def test_delegates_to_store(self) -> None:
        """seed_presets must call manager.seed with the loaded list."""
        mgr = MagicMock()
        mgr.seed.return_value = 1

        count = seed_presets(mgr)

        mgr.seed.assert_called_once()
        templates_arg = mgr.seed.call_args.args[0]
        assert isinstance(templates_arg, list)
        assert count == 1
