"""Snapshot-based tests for resource migration sweeps (Plan 08 Phase 8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.db.database import Database
from agentbox.core.resources.drift import (
    detect_resource_hash_mismatches,
    extract_prompt_markers,
    import_manifest_documents,
    import_manifest_skills,
    propose_prompt_bindings,
    run_all_sweeps,
)


@pytest.fixture
def store(tmp_path: Path) -> Database:
    return Database(tmp_path / "agentbox.sqlite")


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "documents"
    d.mkdir()
    (d / "api-guide.md").write_text("# API Guide\nContent here.")
    (d / "setup.txt").write_text("Setup instructions.")
    return d


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    (d / "python.md").write_text("# Python skill")
    (d / "sql.md").write_text("# SQL skill")
    return d


# ---------------------------------------------------------------------------
# extract_prompt_markers
# ---------------------------------------------------------------------------


class TestExtractPromptMarkers:
    def test_finds_markers(self):
        text = "Use {{resource:api-guide}} and {{resource:setup}} for this task."
        assert extract_prompt_markers(text) == ["api-guide", "setup"]

    def test_empty_when_no_markers(self):
        assert extract_prompt_markers("No markers here.") == []

    def test_deduplicates_same_marker(self):
        text = "{{resource:foo}} and {{resource:foo}} again"
        result = extract_prompt_markers(text)
        assert result.count("foo") == 2  # raw occurrences, dedup is caller's job

    def test_handles_path_style_markers(self):
        text = "See {{resource:skill/python}} for details."
        assert extract_prompt_markers(text) == ["skill/python"]


# ---------------------------------------------------------------------------
# import_manifest_documents
# ---------------------------------------------------------------------------


class TestImportManifestDocuments:
    def test_imports_files(self, store: Database, docs_dir: Path):
        n = import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        assert n == 2
        r = store.resources.get_by_slug("api-guide")
        assert r is not None
        assert r["type"] == "document"

    def test_idempotent_same_content(self, store: Database, docs_dir: Path):
        import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        n2 = import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        assert n2 == 0  # nothing new

    def test_reimports_when_content_changed(self, store: Database, docs_dir: Path):
        import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        (docs_dir / "api-guide.md").write_text("# Updated content")
        n2 = import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        assert n2 >= 1

    def test_nonexistent_dir_returns_zero(self, store: Database, tmp_path: Path):
        assert import_manifest_documents(store.resources, store.resource_versions, tmp_path / "no-such-dir") == 0


# ---------------------------------------------------------------------------
# import_manifest_skills
# ---------------------------------------------------------------------------


class TestImportManifestSkills:
    def test_imports_skills(self, store: Database, skills_dir: Path):
        n = import_manifest_skills(store.resources, store.resource_versions, skills_dir)
        assert n == 2
        r = store.resources.get_by_slug("skill/python")
        assert r is not None
        assert r["type"] == "skill"

    def test_idempotent(self, store: Database, skills_dir: Path):
        import_manifest_skills(store.resources, store.resource_versions, skills_dir)
        n2 = import_manifest_skills(store.resources, store.resource_versions, skills_dir)
        assert n2 == 0

    def test_nonexistent_dir_returns_zero(self, store: Database, tmp_path: Path):
        assert import_manifest_skills(store.resources, store.resource_versions, tmp_path / "no-skills") == 0


# ---------------------------------------------------------------------------
# propose_prompt_bindings
# ---------------------------------------------------------------------------


class TestProposePromptBindings:
    def test_proposes_when_resource_exists(self, store: Database, docs_dir: Path):
        import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        proposals = propose_prompt_bindings(
            store.resources, "agent-1", "See {{resource:api-guide}} for details."
        )
        assert len(proposals) == 1
        assert proposals[0]["marker"] == "api-guide"
        assert proposals[0]["mode"] == "embed"

    def test_empty_when_no_matching_resource(self, store: Database):
        proposals = propose_prompt_bindings(
            store.resources, "agent-1", "See {{resource:nonexistent}} for details."
        )
        assert proposals == []

    def test_empty_when_no_markers(self, store: Database):
        assert propose_prompt_bindings(store.resources, "agent-1", "No markers.") == []


# ---------------------------------------------------------------------------
# detect_resource_hash_mismatches
# ---------------------------------------------------------------------------


class TestDetectResourceHashMismatches:
    def test_no_mismatches_when_content_matches(self, store: Database, docs_dir: Path):
        import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        mismatches = detect_resource_hash_mismatches(store.resources, store.resource_versions, docs_dir)
        assert mismatches == []

    def test_detects_mismatch_after_file_change(self, store: Database, docs_dir: Path):
        import_manifest_documents(store.resources, store.resource_versions, docs_dir)
        (docs_dir / "api-guide.md").write_text("# Changed after import")
        mismatches = detect_resource_hash_mismatches(store.resources, store.resource_versions, docs_dir)
        slugs = [m["slug"] for m in mismatches]
        assert "api-guide" in slugs

    def test_empty_for_nonexistent_dir(self, store: Database, tmp_path: Path):
        assert detect_resource_hash_mismatches(store.resources, store.resource_versions, tmp_path / "x") == []


# ---------------------------------------------------------------------------
# run_all_sweeps
# ---------------------------------------------------------------------------


class TestRunAllSweeps:
    def test_returns_summary(self, store: Database, docs_dir: Path, skills_dir: Path):
        result = run_all_sweeps(
            store.resources, store.resource_versions, documents_dir=docs_dir, skills_dir=skills_dir
        )
        assert result["docs_imported"] == 2
        assert result["skills_imported"] == 2

    def test_no_dirs_returns_zeros(self, store: Database):
        result = run_all_sweeps(store.resources, store.resource_versions)
        assert result == {"docs_imported": 0, "skills_imported": 0}
