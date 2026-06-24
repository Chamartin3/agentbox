"""Tests for shared_resources → unified resources migration sweep."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.db import SessionStore
from agentbox.core.resources.migration import (
    KIND_TO_TYPE,
    migrate_shared_resources_to_repo,
)


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "agentbox.sqlite")


def _seed(store: SessionStore, *, kind: str, name: str, content: str = "x") -> None:
    store.create_resource(
        id=f"{kind}-{name}",
        kind=kind,
        name=name,
        content=content,
    )


def test_migrates_each_supported_kind(store: SessionStore) -> None:
    _seed(store, kind="output_schema", name="OutSchema", content='{"type":"object"}')
    _seed(store, kind="input_schema", name="InSchema", content='{"type":"object"}')
    _seed(store, kind="user_template", name="UserTpl")
    _seed(store, kind="system_fragment", name="SysFrag")
    _seed(store, kind="reference", name="Ref")
    _seed(store, kind="skill", name="MySkill")

    report = migrate_shared_resources_to_repo(store)
    assert report.summary()["migrated"] == 6
    assert report.failed == []

    all_repo = store.list_repo_resources(limit=100)
    types = sorted(r["type"] for r in all_repo)
    assert types == ["document", "document", "document", "schema", "schema", "skill"]


def test_skips_mcp_server_kind(store: SessionStore) -> None:
    _seed(store, kind="mcp_server", name="srv")
    report = migrate_shared_resources_to_repo(store)
    assert report.summary()["skipped_kinds"] == 1
    assert report.summary()["migrated"] == 0


def test_idempotent_second_run(store: SessionStore) -> None:
    _seed(store, kind="reference", name="r1")
    first = migrate_shared_resources_to_repo(store)
    second = migrate_shared_resources_to_repo(store)
    assert first.summary()["migrated"] == 1
    assert second.summary()["migrated"] == 0
    assert second.summary()["skipped_existing"] == 1


def test_kind_map_only_has_known_targets() -> None:
    assert set(KIND_TO_TYPE.values()) <= {"schema", "document", "skill"}
