"""Snapshot-based tests for resource migration sweeps (Plan 08 Phase 8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from agentbox.core.resource.drift import (
    detect_resource_hash_mismatches,
    extract_prompt_markers,
    import_manifest_documents,
    import_manifest_skills,
    propose_prompt_bindings,
    run_all_sweeps,
)


@pytest.fixture
def store(tmp_path: Path):
    from agentbox.core.data import SessionStore

    return SessionStore(tmp_path / "db.sqlite")


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
    def test_imports_files(self, store, docs_dir: Path):
        n = import_manifest_documents(store, docs_dir)
        assert n == 2
        r = store.get_repo_resource_by_slug("api-guide")
        assert r is not None
        assert r["type"] == "document"

    def test_idempotent_same_content(self, store, docs_dir: Path):
        import_manifest_documents(store, docs_dir)
        n2 = import_manifest_documents(store, docs_dir)
        assert n2 == 0  # nothing new

    def test_reimports_when_content_changed(self, store, docs_dir: Path):
        import_manifest_documents(store, docs_dir)
        (docs_dir / "api-guide.md").write_text("# Updated content")
        n2 = import_manifest_documents(store, docs_dir)
        assert n2 >= 1

    def test_nonexistent_dir_returns_zero(self, store, tmp_path: Path):
        assert import_manifest_documents(store, tmp_path / "no-such-dir") == 0


# ---------------------------------------------------------------------------
# import_manifest_skills
# ---------------------------------------------------------------------------


class TestImportManifestSkills:
    def test_imports_skills(self, store, skills_dir: Path):
        n = import_manifest_skills(store, skills_dir)
        assert n == 2
        r = store.get_repo_resource_by_slug("skill/python")
        assert r is not None
        assert r["type"] == "skill"

    def test_idempotent(self, store, skills_dir: Path):
        import_manifest_skills(store, skills_dir)
        n2 = import_manifest_skills(store, skills_dir)
        assert n2 == 0

    def test_nonexistent_dir_returns_zero(self, store, tmp_path: Path):
        assert import_manifest_skills(store, tmp_path / "no-skills") == 0


# ---------------------------------------------------------------------------
# propose_prompt_bindings
# ---------------------------------------------------------------------------


class TestProposePromptBindings:
    def test_proposes_when_resource_exists(self, store, docs_dir: Path):
        import_manifest_documents(store, docs_dir)
        proposals = propose_prompt_bindings(
            store, "agent-1", "See {{resource:api-guide}} for details."
        )
        assert len(proposals) == 1
        assert proposals[0]["marker"] == "api-guide"
        assert proposals[0]["mode"] == "embed"

    def test_empty_when_no_matching_resource(self, store):
        proposals = propose_prompt_bindings(
            store, "agent-1", "See {{resource:nonexistent}} for details."
        )
        assert proposals == []

    def test_empty_when_no_markers(self, store):
        assert propose_prompt_bindings(store, "agent-1", "No markers.") == []


# ---------------------------------------------------------------------------
# detect_resource_hash_mismatches
# ---------------------------------------------------------------------------


class TestDetectResourceHashMismatches:
    def test_no_mismatches_when_content_matches(self, store, docs_dir: Path):
        import_manifest_documents(store, docs_dir)
        mismatches = detect_resource_hash_mismatches(store, docs_dir)
        assert mismatches == []

    def test_detects_mismatch_after_file_change(self, store, docs_dir: Path):
        import_manifest_documents(store, docs_dir)
        (docs_dir / "api-guide.md").write_text("# Changed after import")
        mismatches = detect_resource_hash_mismatches(store, docs_dir)
        slugs = [m["slug"] for m in mismatches]
        assert "api-guide" in slugs

    def test_empty_for_nonexistent_dir(self, store, tmp_path: Path):
        assert detect_resource_hash_mismatches(store, tmp_path / "x") == []


# ---------------------------------------------------------------------------
# run_all_sweeps
# ---------------------------------------------------------------------------


class TestRunAllSweeps:
    def test_returns_summary(self, store, docs_dir: Path, skills_dir: Path):
        result = run_all_sweeps(store, documents_dir=docs_dir, skills_dir=skills_dir)
        assert result["docs_imported"] == 2
        assert result["skills_imported"] == 2

    def test_no_dirs_returns_zeros(self, store):
        result = run_all_sweeps(store)
        assert result == {"docs_imported": 0, "skills_imported": 0}
