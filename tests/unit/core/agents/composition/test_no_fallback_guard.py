"""Guard test: build_prompt raises (not silently falls back) when an agent
has no composition block.

This invariant is enforced by plan 147: all creation paths call
``inline_to_composition()`` and the 0011 migration backfills existing rows.
After that, a version reaching ``build_prompt`` without a block is a data
error that must fail loud — not produce an empty or incorrect system prompt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agentbox.core.agents.composition.build import (
    BuildManagers,
    build_prompt,
)
from agentbox.core.data.manifests.agents import AgentDef
from agentbox.core.config import load_settings


def _minimal_managers() -> BuildManagers:
    """BuildManagers with stub managers — enough for build_prompt to get past
    the composition guard (which fires before any manager call)."""
    mgr = MagicMock()
    return BuildManagers(
        agent_prompt_resource_bindings=mgr,
        resources=mgr,
        resource_versions=mgr,
        resource_blobs=mgr,
        agent_versions=mgr,
        agent_version_files=mgr,
    )


def test_build_prompt_raises_when_composition_is_none() -> None:
    """A version without a composition block must raise ValueError, not fall back."""
    agent = AgentDef(id="no-comp-agent", prompt="some text", composition=None)
    with pytest.raises(ValueError, match="no composition block"):
        build_prompt(
            managers=_minimal_managers(),
            settings=load_settings(),
            agent=agent,
            input_="hello",
            variables={"user_message": "hello"},
        )


def test_build_prompt_raises_error_mentions_migration() -> None:
    """Error message must guide users to run the migration."""
    agent = AgentDef(id="no-comp-agent", prompt="p", composition=None)
    with pytest.raises(ValueError, match="0011"):
        build_prompt(
            managers=_minimal_managers(),
            settings=load_settings(),
            agent=agent,
            input_="",
            variables={},
        )


def test_build_prompt_raises_with_variables_none() -> None:
    """The guard fires regardless of whether variables is None or a dict."""
    agent = AgentDef(id="no-comp-agent", prompt="p", composition=None)
    with pytest.raises(ValueError, match="no composition block"):
        build_prompt(
            managers=_minimal_managers(),
            settings=load_settings(),
            agent=agent,
            input_="raw input",
            variables=None,
        )
