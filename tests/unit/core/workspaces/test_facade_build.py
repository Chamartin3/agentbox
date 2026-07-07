"""Workspaces facade — compose → render parity (plan 118 Phase E).

Mirrors the old ``build_workspace`` behavior against the new
``Workspaces.build`` facade: persistent builds write env-doc + provenance;
run builds (``into=path``) render identical content but skip provenance;
ephemeral never touches disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from agentbox.core.config import Settings
from agentbox.core.db import WorkspaceReadManager
from agentbox.core.db.database import Database
from agentbox.core.workspaces.facade import Workspaces


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return cast(
        Settings,
        SimpleNamespace(
            project_root=tmp_path,
            workspaces_root=tmp_path / "workspaces",
            resource_cache_dir=tmp_path / "cache",
        ),
    )


def _workspaces(db: Database, settings: Settings) -> Workspaces:
    return Workspaces(WorkspaceReadManager(db._engine), settings)


def _seed_workspace(db: Database, name: str) -> None:
    db.workspaces.upsert(name, path=f"workdir/{name}", source="db")


def _save_env_doc(db: Database, workspace_id: str) -> None:
    # Env docs are stored as {"body": <markdown>} (see WorkspacesService).
    db.workspace_env_doc_versions.save(
        workspace_id,
        {"body": "# Test Workspace\n\nIntegration testing"},
        changelog="seed",
        publish=True,
    )


def test_persistent_build_writes_env_doc_and_provenance(
    db: Database, settings: Settings, tmp_path: Path
) -> None:
    _seed_workspace(db, "default")
    _save_env_doc(db, "default")

    result = _workspaces(db, settings).build("default")

    workdir = tmp_path / "workdir" / "default"
    assert result.target_dir == workdir
    assert (workdir / "CLAUDE.md").exists()
    assert (workdir / "AGENTS.md").exists()
    meta = json.loads((workdir / ".agentbox" / "meta.json").read_text())
    assert meta["workspace_id"] == "default"
    assert set(meta["env_doc_files"]) == {"CLAUDE.md", "AGENTS.md"}
    assert result.errors == []


def test_ephemeral_build_touches_no_disk(
    db: Database, settings: Settings, tmp_path: Path
) -> None:
    result = _workspaces(db, settings).build("<ephemeral>")
    assert result.env_doc_files == []
    assert result.target_dir == Path()
    assert not (tmp_path / "workdir").exists()


def test_run_build_into_dir_renders_without_provenance(
    db: Database, settings: Settings, tmp_path: Path
) -> None:
    _seed_workspace(db, "default")
    _save_env_doc(db, "default")
    run_dir = tmp_path / "runs" / "abc123"

    result = _workspaces(db, settings).build("default", into=run_dir)

    assert result.target_dir == run_dir
    assert (run_dir / "CLAUDE.md").exists()
    # Claude's --strict-mcp-config needs an .mcp.json even with no servers.
    assert (run_dir / ".mcp.json").exists()
    # Run dirs are ephemeral: no orphan-reconcile / provenance file.
    assert not (run_dir / ".agentbox" / "meta.json").exists()


def test_no_env_doc_persistent_still_writes_provenance(
    db: Database, settings: Settings, tmp_path: Path
) -> None:
    _seed_workspace(db, "barebones")

    result = _workspaces(db, settings).build("barebones")

    workdir = tmp_path / "workdir" / "barebones"
    # No env-doc body → nothing recorded in provenance's env_doc_files.
    assert result.env_doc_files == []
    # Decision 2: native config generation runs for the persistent workdir too,
    # so an (empty) instruction file is emitted even without an env-doc body.
    # (Old build_workspace never wrote native config into the persistent dir.)
    assert (workdir / ".agentbox" / "meta.json").exists()


# ── render_env_doc: env-doc-only render into an arbitrary dir ────────────────


def test_render_env_doc_writes_both_files_and_entries(
    db: Database, settings: Settings, tmp_path: Path
) -> None:
    _seed_workspace(db, "default")
    _save_env_doc(db, "default")
    out = tmp_path / "preview"

    entries = _workspaces(db, settings).render_env_doc("default", out)

    body = "# Test Workspace\n\nIntegration testing"
    assert (out / "CLAUDE.md").read_text() == body
    assert (out / "AGENTS.md").read_text() == body
    # env-doc-only: no native config written into the target dir.
    assert not (out / ".mcp.json").exists()
    assert {e["file"] for e in entries} == {"CLAUDE.md", "AGENTS.md"}
    assert {e["role"] for e in entries} == {"env_doc"}
    assert all(e["workspace_id"] == "default" and e["bytes"] > 0 for e in entries)


def test_render_env_doc_ephemeral_is_empty(
    db: Database, settings: Settings, tmp_path: Path
) -> None:
    assert _workspaces(db, settings).render_env_doc("<ephemeral>", tmp_path) == []


def test_render_env_doc_no_active_doc_is_empty(
    db: Database, settings: Settings, tmp_path: Path
) -> None:
    _seed_workspace(db, "nodoc")
    assert _workspaces(db, settings).render_env_doc("nodoc", tmp_path) == []
