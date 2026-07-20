"""Tests for the agentbox resource CLI sub-app."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.db.database import Database
from agentbox.cli import app
from agentbox.core.service.resources import ResourceService
from agentbox.cli.shared import (
    get_executor,
    get_mcp_registry,
)
from agentbox.cli.shared.deps import (
    get_resource_service,
    get_settings,
)
from typer.testing import CliRunner

runner = CliRunner()


def _clear_shared_deps_caches() -> None:
    """Clear agentbox.cli.shared.deps lru_caches.

    The autouse conftest clears ``agentbox.cli.shared.deps``. Commands in
    ``ops resource`` and ``ops resource bind`` import ``get_store`` from
    ``agentbox.cli.shared``, which must be cleared independently so each
    test gets a fresh store pointed at its own tmp_path.
    """
    for fn in (get_settings, get_executor, get_mcp_registry, get_resource_service):
        fn.cache_clear()


@pytest.fixture
def store_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated store pointing at tmp_path.

    Relies on the autouse ``_reset_agentbox_deps_caches`` fixture in
    ``tests/integration/conftest.py`` to clear caches between tests.
    Also clears ``agentbox.cli.shared.deps`` caches explicitly since
    commands under ``ops resource`` import from ``agentbox.cli.shared``.
    """
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTBOX_SKIP_DEFAULT_PROFILES", "1")
    _clear_shared_deps_caches()
    store = Database(get_settings().db_path)
    yield store
    _clear_shared_deps_caches()


# ---------------------------------------------------------------------------
# ops resource repo ls
# ---------------------------------------------------------------------------


def test_resource_list_empty(store_fixture) -> None:
    result = runner.invoke(app, ["ops", "resource", "repo", "ls"])
    assert result.exit_code == 0
    assert "No resources" in result.output


def test_resource_list_shows_resource(store_fixture) -> None:
    ResourceService().create_resource(slug="my-doc", type="document", display_name="My Doc")
    result = runner.invoke(app, ["ops", "resource", "repo", "ls"])
    assert result.exit_code == 0
    assert "my-doc" in result.output


def test_resource_list_type_filter(store_fixture) -> None:
    ResourceService().create_resource(slug="skill-a", type="skill", display_name="Skill A")
    ResourceService().create_resource(slug="doc-b", type="document", display_name="Doc B")
    result = runner.invoke(app, ["ops", "resource", "repo", "ls", "--type", "skill"])
    assert result.exit_code == 0
    assert "skill-a" in result.output
    assert "doc-b" not in result.output


# ---------------------------------------------------------------------------
# ops resource repo show
# ---------------------------------------------------------------------------


def test_resource_show_not_found(store_fixture) -> None:
    result = runner.invoke(app, ["ops", "resource", "repo", "show", "no-such-slug"])
    assert result.exit_code == 2


def test_resource_show_existing(store_fixture) -> None:
    ResourceService().create_resource(slug="test-slug", type="document", display_name="Test Resource")
    result = runner.invoke(app, ["ops", "resource", "repo", "show", "test-slug"])
    assert result.exit_code == 0
    assert "test-slug" in result.output


# ---------------------------------------------------------------------------
# ops resource repo upload
# ---------------------------------------------------------------------------


def test_resource_upload_creates_version(store_fixture, tmp_path: Path) -> None:
    src = tmp_path / "hello.txt"
    src.write_text("hello world")
    # Create the resource first
    ResourceService().create_resource(slug="upload-test", type="document", display_name="Upload Test")
    result = runner.invoke(
        app,
        [
            "ops",
            "resource",
            "repo",
            "upload",
            "upload-test",
            str(src),
            "--changelog",
            "initial upload",
        ],
    )
    assert result.exit_code == 0
    assert "version" in result.output


def test_resource_upload_rejects_short_changelog(store_fixture, tmp_path: Path) -> None:
    src = tmp_path / "file.txt"
    src.write_text("data")
    result = runner.invoke(
        app, ["ops", "resource", "repo", "upload", "some-slug", str(src), "--changelog", "ab"]
    )
    assert result.exit_code == 1
    assert "at least 3" in result.output


def test_resource_upload_missing_file(store_fixture) -> None:
    result = runner.invoke(
        app,
        ["ops", "resource", "repo", "upload", "x", "/no/such/path.txt", "--changelog", "valid reason"],
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# ops resource repo rollback
# ---------------------------------------------------------------------------


def test_resource_rollback_rejects_short_changelog(store_fixture) -> None:
    result = runner.invoke(
        app, ["ops", "resource", "repo", "rollback", "my-res", "1", "--changelog", "ab"]
    )
    assert result.exit_code == 1


def test_resource_rollback_not_found(store_fixture) -> None:
    result = runner.invoke(
        app, ["ops", "resource", "repo", "rollback", "no-such", "1", "--changelog", "valid reason"]
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# ops resource bind list
# ---------------------------------------------------------------------------


def test_prompt_bindings_list_empty(store_fixture) -> None:
    result = runner.invoke(app, ["ops", "resource", "bind", "list", "agent-x"])
    assert result.exit_code == 0
    assert "No prompt bindings" in result.output


# ---------------------------------------------------------------------------
# ops resource bind set
# ---------------------------------------------------------------------------


def test_prompt_bindings_set_rejects_short_reason(store_fixture) -> None:
    result = runner.invoke(
        app,
        ["ops", "resource", "bind", "set", "agent-x", "DOCS", "my-slug", "--reason", "ab"],
    )
    assert result.exit_code == 1
    assert "at least 3" in result.output


def test_prompt_bindings_set_missing_resource(store_fixture) -> None:
    result = runner.invoke(
        app,
        [
            "ops",
            "resource",
            "bind",
            "set",
            "agent-x",
            "DOCS",
            "no-resource",
            "--reason",
            "valid reason",
        ],
    )
    assert result.exit_code == 2


def test_prompt_bindings_set_and_list(store_fixture) -> None:
    ResourceService().create_resource(slug="kb-docs", type="document", display_name="KB Docs")
    result = runner.invoke(
        app,
        [
            "ops",
            "resource",
            "bind",
            "set",
            "agent-x",
            "DOCS",
            "kb-docs",
            "--mode",
            "inline",
            "--reason",
            "adding knowledge base",
        ],
    )
    assert result.exit_code == 0

    result2 = runner.invoke(app, ["ops", "resource", "bind", "list", "agent-x"])
    assert result2.exit_code == 0
    assert "DOCS" in result2.output
    assert "kb-docs" not in result2.output  # shows resource_id, not slug


# ---------------------------------------------------------------------------
# work res ls
# ---------------------------------------------------------------------------


def test_workspace_resources_list_empty(store_fixture) -> None:
    result = runner.invoke(app, ["work", "res", "ls", "ws-x"])
    assert result.exit_code == 0
    assert "No file bindings" in result.output


# ---------------------------------------------------------------------------
# work res set
# ---------------------------------------------------------------------------


def test_workspace_resources_set_rejects_short_reason(store_fixture) -> None:
    result = runner.invoke(
        app,
        ["work", "res", "set", "ws-x", "docs/", "some-slug", "--reason", "ab"],
    )
    assert result.exit_code == 1


def test_workspace_resources_set_missing_resource(store_fixture) -> None:
    result = runner.invoke(
        app,
        [
            "work",
            "res",
            "set",
            "ws-x",
            "docs/",
            "missing-slug",
            "--reason",
            "good reason",
        ],
    )
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# work res check (dry-run)
# ---------------------------------------------------------------------------


def test_workspace_resources_dry_run_empty(store_fixture) -> None:
    result = runner.invoke(app, ["work", "res", "check", "ws-none"])
    assert result.exit_code == 0
    assert "No workspace resource bindings" in result.output


# ---------------------------------------------------------------------------
# env-doc
# ---------------------------------------------------------------------------


def test_env_doc_show_empty(store_fixture) -> None:
    result = runner.invoke(app, ["system", "env", "show", "ws-x"])
    assert result.exit_code == 0
    assert "No active env doc" in result.output


def test_env_doc_versions_empty(store_fixture) -> None:
    result = runner.invoke(app, ["system", "env", "versions", "ws-x"])
    assert result.exit_code == 0
    assert "No env doc versions" in result.output


def test_env_doc_edit_rejects_short_changelog(store_fixture) -> None:
    result = runner.invoke(app, ["system", "env", "edit", "ws-x", "{}", "--changelog", "ab"])
    assert result.exit_code == 1


def test_env_doc_edit_saves_and_shows(store_fixture) -> None:
    result = runner.invoke(
        app,
        [
            "system",
            "env",
            "edit",
            "ws-test",
            '{"note": "hello"}',
            "--changelog",
            "initial doc",
        ],
    )
    assert result.exit_code == 0
    assert "version" in result.output


def test_env_doc_rollback_rejects_short_changelog(store_fixture) -> None:
    result = runner.invoke(
        app, ["system", "env", "rollback", "ws-x", "some-id", "--changelog", "ab"]
    )
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# host-env
# ---------------------------------------------------------------------------


def test_host_env_profiles_empty(store_fixture) -> None:
    result = runner.invoke(app, ["system", "host", "profiles"])
    assert result.exit_code == 0
    assert "No host-env profiles" in result.output


def test_host_env_grants_empty(store_fixture) -> None:
    result = runner.invoke(app, ["system", "host", "grants", "ws-x"])
    assert result.exit_code == 0
    assert "No host-env grant" in result.output


def test_host_env_audit_empty(store_fixture) -> None:
    result = runner.invoke(app, ["system", "host", "audit", "run-xyz"])
    assert result.exit_code == 0
    assert "No host-env calls" in result.output


# ---------------------------------------------------------------------------
# work mcp
# ---------------------------------------------------------------------------


def test_mcp_workspace_show(store_fixture) -> None:
    result = runner.invoke(app, ["work", "mcp", "show", "ws-x"])
    assert result.exit_code == 0
    assert "allow_all_unless_disabled" in result.output


def test_mcp_workspace_policy_invalid(store_fixture) -> None:
    result = runner.invoke(app, ["work", "mcp", "policy", "ws-x", "bad-policy"])
    assert result.exit_code == 1


def test_mcp_workspace_policy_valid(store_fixture) -> None:
    result = runner.invoke(
        app, ["work", "mcp", "policy", "ws-x", "deny_all_unless_enabled"]
    )
    assert result.exit_code == 0
    assert "deny_all_unless_enabled" in result.output


def test_mcp_workspace_enable_rejects_short_reason(store_fixture) -> None:
    result = runner.invoke(
        app, ["work", "mcp", "toggle", "ws-x", "my-server", "--reason", "ab"]
    )
    assert result.exit_code == 1


def test_mcp_workspace_enable_valid(store_fixture) -> None:
    result = runner.invoke(
        app,
        [
            "work",
            "mcp",
            "toggle",
            "ws-x",
            "my-server",
            "--reason",
            "enabling for test",
        ],
    )
    assert result.exit_code == 0


def test_mcp_workspace_disable_valid(store_fixture) -> None:
    result = runner.invoke(
        app,
        [
            "work",
            "mcp",
            "toggle",
            "ws-x",
            "my-server",
            "--off",
            "--reason",
            "disabling for test",
        ],
    )
    assert result.exit_code == 0
