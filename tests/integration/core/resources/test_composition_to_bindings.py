"""Boot-import sweep: composition.references → resources + prompt bindings."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from agentbox.core.data import CompositionConfig
from agentbox.core.db.database import Database
from agentbox.core.resources.boot import import_composition_references


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


def _seed_shared_file(root: Path, rel: str, body: str) -> Path:
    p = root / "shared" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _agent(agent_id: str, refs: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        id=agent_id,
        composition=CompositionConfig(references=refs),
        source_path=None,
    )


def test_imports_shared_uri_refs_and_creates_bindings(
    store: Database, tmp_path: Path
) -> None:
    _seed_shared_file(tmp_path, "drafting/guidelines/voice.md", "# Voice\n")
    _seed_shared_file(tmp_path, "drafting/guidelines/tone.md", "# Tone\n")

    agent = _agent(
        "draft.writer_v3",
        [
            "shared://drafting/guidelines/voice.md",
            "shared://drafting/guidelines/tone.md",
        ],
    )
    manifest = SimpleNamespace(agents=[agent])

    summary = import_composition_references(
        store.resources, store.resource_versions, store.agent_prompt_resource_bindings, tmp_path, manifest
    )

    assert summary["agents_wired"] == 1
    assert summary["resources_created"] == 2
    assert summary["bindings_added"] == 2

    voice = store.resources.get_by_slug("shared:drafting/guidelines/voice.md")
    tone = store.resources.get_by_slug("shared:drafting/guidelines/tone.md")
    assert voice is not None and voice["type"] == "document"
    assert tone is not None and tone["type"] == "document"

    bindings = store.agent_prompt_resource_bindings.list_for_agent("draft.writer_v3")
    assert len(bindings) == 2
    assert all(b["attach_as_reference"] for b in bindings)
    assert {b["resource_id"] for b in bindings} == {voice["id"], tone["id"]}


def test_skips_agents_with_existing_bindings(
    store: Database, tmp_path: Path
) -> None:
    _seed_shared_file(tmp_path, "drafting/voice.md", "# Voice\n")
    agent = _agent("draft.writer", ["shared://drafting/voice.md"])
    manifest = SimpleNamespace(agents=[agent])

    # First sweep wires bindings.
    s1 = import_composition_references(
        store.resources, store.resource_versions, store.agent_prompt_resource_bindings, tmp_path, manifest
    )
    assert s1["bindings_added"] == 1

    # Second sweep is a no-op (existing bindings are not trampled).
    s2 = import_composition_references(
        store.resources, store.resource_versions, store.agent_prompt_resource_bindings, tmp_path, manifest
    )
    assert s2["agents_wired"] == 0
    assert s2["bindings_added"] == 0


def test_missing_ref_file_is_skipped_with_warning(
    store: Database, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _seed_shared_file(tmp_path, "drafting/exists.md", "ok")
    agent = _agent(
        "draft.writer",
        ["shared://drafting/exists.md", "shared://drafting/missing.md"],
    )
    manifest = SimpleNamespace(agents=[agent])

    with caplog.at_level("WARNING"):
        summary = import_composition_references(
            store.resources, store.resource_versions, store.agent_prompt_resource_bindings, tmp_path, manifest
        )

    assert summary["bindings_added"] == 1
    assert any("not found on disk" in r.message for r in caplog.records)
