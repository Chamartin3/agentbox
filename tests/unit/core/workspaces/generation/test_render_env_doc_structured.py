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
from agentbox.core.workspaces.generation.recipe import load_recipe

_BODY = "# Acme\n\nDo the thing. Then verify it.\n"


def _config() -> WorkenvConfig:
    return WorkenvConfig(name="ws", env_doc=_BODY)


def test_claude_context_is_raw_body() -> None:
    with tempfile.TemporaryDirectory() as td:
        render(Path(td), _config(), load_recipe("claude_code"))
        assert (Path(td) / "CLAUDE.md").read_text() == _BODY
        assert not (Path(td) / "AGENTS.md").exists()


def test_opencode_context_is_raw_body() -> None:
    with tempfile.TemporaryDirectory() as td:
        render(Path(td), _config(), load_recipe("opencode"))
        # opencode reads AGENTS.md (same body), plus its own opencode.json blob.
        assert (Path(td) / "AGENTS.md").read_text() == _BODY
        assert (Path(td) / "opencode.json").exists()
        assert not (Path(td) / "CLAUDE.md").exists()


if __name__ == "__main__":
    test_claude_context_is_raw_body()
    test_opencode_context_is_raw_body()
    print("ok")
