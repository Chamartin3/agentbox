"""Env-doc is plain text placed by the recipe ``context`` layout.

The env-doc body goes verbatim into each engine's instruction file —
CLAUDE.md (claude_code) and AGENTS.md (opencode) — identical content for
every engine, no structure and no audience filtering.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agentbox.core.workspaces.generation.config import WorkenvConfig
from agentbox.core.workspaces.generation.generator import render
from agentbox.core.engines.backends.recipe_loader import load_recipe, backend_for_engine

_BODY = "# Acme\n\nDo the thing. Then verify it.\n"


def _config() -> WorkenvConfig:
    return WorkenvConfig(name="ws", env_doc=_BODY)


def test_claude_context_is_raw_body() -> None:
    with tempfile.TemporaryDirectory() as td:
        config = _config()
        recipe = load_recipe("claude_code")
        try:
            extra = backend_for_engine("claude_code").build_workspace_items(config)
        except KeyError:
            extra = []
        render(Path(td), config, recipe, extra_items=extra)
        assert (Path(td) / "CLAUDE.md").read_text() == _BODY
        assert not (Path(td) / "AGENTS.md").exists()


def test_opencode_context_is_raw_body() -> None:
    with tempfile.TemporaryDirectory() as td:
        config = _config()
        recipe = load_recipe("opencode")
        try:
            extra = backend_for_engine("opencode").build_workspace_items(config)
        except KeyError:
            extra = []
        render(Path(td), config, recipe, extra_items=extra)
        # opencode reads AGENTS.md (same body), plus its own opencode.json blob.
        assert (Path(td) / "AGENTS.md").read_text() == _BODY
        assert (Path(td) / "opencode.json").exists()
        assert not (Path(td) / "CLAUDE.md").exists()


if __name__ == "__main__":
    test_claude_context_is_raw_body()
    test_opencode_context_is_raw_body()
    print("ok")
