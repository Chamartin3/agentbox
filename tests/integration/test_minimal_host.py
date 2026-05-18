"""Minimal host contract tests.

Verify that agentbox can start and serve requests when ONLY the required
manifest mount is present — all optional bind-mounts absent.

These tests use the in-process FastAPI TestClient (no Docker required).
They exercise the boundary described in the Plan-08 "Done" criterion:

    "a container with only the manifest mount can serve a run"

Runs use a noop BackendAdapter registered per-test so no real subprocess
is needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Noop backend registration
# ---------------------------------------------------------------------------


def _register_noop_backend() -> None:
    """Inject a noop BackendAdapter into the plugins registry under 'claude_code'.

    Uses an existing RunnerKind value so manifests pass Pydantic validation,
    while the actual subprocess is never invoked.
    """
    from agentbox.api.events import DoneEvent, RunEvent
    from agentbox.core.run.backends.base import RenderedConfig

    class _NoopBackend:
        name = "claude_code"

        def render(self, agent: Any, workdir: Path, mcp_tools: Any = None, creds: Any = None, runner_config: Any = None) -> RenderedConfig:
            return RenderedConfig(files={}, argv=["true"], env={}, cwd=Path("."))

        async def run(  # type: ignore[override]
            self, rendered: RenderedConfig, input: str, run_id: str
        ) -> AsyncIterator[RunEvent]:
            yield DoneEvent(run_id=run_id, ok=True, output="noop done")

    import agentbox.core.agent.plugins as _plugins

    _plugins.backends()  # warm the cache
    _plugins._BACKEND_CLASSES["claude_code"] = _NoopBackend  # type: ignore[index]


_NOOP_AGENT_TOML = """\
[[agents]]
id = "noop"
description = "No-op agent for host contract verification"
session_mode = "headless"
headless = true

  [agents.runner]
  kind = "claude_code"
  timeout_seconds = 5
"""

_NOOP_MCP_SERVER_TOML = """\
[[mcp_servers]]
name = "my-mcp"
url = "http://mcp-server:8001/mcp/"
transport = "http"
cache_ttl = 300
"""


# ---------------------------------------------------------------------------
# Tests — build on the shared `client` + `isolated_data_dir` fixtures
# ---------------------------------------------------------------------------


def test_health_with_only_manifest(client: Any) -> None:
    """Health endpoint returns 200 with only the manifest mount."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_agents_list_empty_with_minimal_manifest(client: Any) -> None:
    """/api/agents returns an empty list for a minimal (agent-free) manifest."""
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_agents_list_with_noop_agent(isolated_data_dir: Path, client: Any) -> None:
    """Agents defined in the manifest are listed after the cache is re-warmed."""
    _register_noop_backend()

    # Write a manifest with a noop agent (isolated_data_dir already set the
    # path; overwrite the file and clear the loader cache so the route re-reads it)
    manifest = isolated_data_dir / "manifest.toml"
    manifest.write_text(_NOOP_AGENT_TOML)

    import agentbox.api.deps as deps

    deps.get_loader.cache_clear()

    resp = client.get("/api/agents")
    assert resp.status_code == 200
    ids = [a["id"] for a in resp.json()]
    assert "noop" in ids


def test_optional_mounts_absent_from_settings(
    isolated_data_dir: Path,
) -> None:
    """With only AGENTBOX_MANIFEST set, all optional dirs resolve to None."""
    # _scrub_agentbox_env (autouse) already deleted optional env vars;
    # isolated_data_dir set AGENTBOX_MANIFEST only.
    from agentbox.config import SETTINGS

    assert SETTINGS.agents_dir is None
    assert SETTINGS.prompts_dir is None
    assert SETTINGS.skills_dir is None
    assert SETTINGS.outputs_dir is None


def test_workspaces_root_absent_does_not_crash(
    isolated_data_dir: Path, client: Any
) -> None:
    """workspaces_root need not exist on disk — the app serves requests cleanly."""
    from agentbox.config import SETTINGS

    assert not SETTINGS.workspaces_root.exists()

    resp = client.get("/api/agents")
    assert resp.status_code == 200


def test_run_with_noop_agent(isolated_data_dir: Path, client: Any) -> None:
    """POST /api/runs completes when only the manifest is present."""
    _register_noop_backend()

    manifest = isolated_data_dir / "manifest.toml"
    manifest.write_text(_NOOP_AGENT_TOML)

    import agentbox.api.deps as deps

    deps.get_loader.cache_clear()
    deps.get_executor.cache_clear()

    resp = client.post("/api/runs", json={"agent": "noop", "input": "ping"})
    assert resp.status_code in (200, 201, 202), resp.text
    assert "run_id" in resp.json()


def test_missing_manifest_emits_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check_manifest() raises RuntimeError with a clear message when absent."""
    import importlib

    monkeypatch.setenv("AGENTBOX_MANIFEST", str(tmp_path / "nonexistent.toml"))

    import agentbox.config as _config

    importlib.reload(_config)

    from agentbox.config import SETTINGS

    with pytest.raises(RuntimeError, match="agentbox cannot start"):
        SETTINGS.check_manifest()


def test_mcp_servers_in_manifest_parse(isolated_data_dir: Path) -> None:
    """[[mcp_servers]] block in manifest parses correctly (new TOML format)."""
    manifest = isolated_data_dir / "manifest.toml"
    manifest.write_text(_NOOP_MCP_SERVER_TOML)

    from agentbox.core.deprecated.definitions import DefinitionLoader

    loader = DefinitionLoader(isolated_data_dir)
    m = loader.load()
    assert len(m.mcp_servers) == 1
    assert m.mcp_servers[0].name == "my-mcp"
    assert m.mcp_servers[0].url == "http://mcp-server:8001/mcp/"
    assert m.mcp_servers[0].cache_ttl == 300
