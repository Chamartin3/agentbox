"""Regression: GET /api/agents/{id} must surface a composed_system even
when the active version has no captured bundle files in the DB
(falls back to FilesystemBundleSource via capture_bundle_files).

Driven by user report: draft_improver had composition.references but the
detail endpoint returned ``composed_system: ''`` and the UI Composition
tab was blank.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from agentbox.api.app import create_app
from fastapi.testclient import TestClient


def _bootstrap(tmp_path: Path) -> None:
    agents_d = tmp_path / "agents.d"
    agents_d.mkdir(parents=True, exist_ok=True)
    bundle = agents_d / "demo"
    (bundle / "prompts").mkdir(parents=True)
    (bundle / "prompts" / "system.md").write_text("# Demo system\nHello.")
    (bundle / "agent.toml").write_text(
        'id = "demo"\n'
        'description = "demo"\n'
        "[composition]\n"
        'system = "prompts/system.md"\n'
    )


def test_composed_system_falls_back_to_disk(isolated_data_dir: Path) -> None:
    _bootstrap(isolated_data_dir)
    import agentbox.api.deps as deps

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_loader,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()

    client = TestClient(create_app())
    try:
        client.__enter__()
        store = deps.get_store()
        # Strip the captured bundle files so the route must use the disk
        # fallback to render the composition preview.
        active = store.get_active_version("demo") or store.latest_version("demo")
        assert active is not None
        store.delete_version_files(active["id"])

        resp = client.get("/api/agents/demo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["composed_system"], (
            "composed_system must be rendered from disk when DB bundle "
            f"files are missing — got {body['composed_system']!r}"
        )
        assert "Demo system" in body["composed_system"]
    finally:
        with contextlib.suppress(Exception):
            client.__exit__(None, None, None)
