"""Unit tests for `core/resources/binding_materialize.py`.

Covers:
- ``_resolve_single_file_name``: three-step filename precedence
  (source_metadata.filename > host_path > display_name).
- ``materialize_workspace``: on_conflict policy (error / skip / overwrite)
  and MaterializeOutcome correctness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentbox.core.workspaces.generation.materialize import (
    MaterializeOutcome,
    _resolve_single_file_name,
    materialize_workspace,
)


# ---------------------------------------------------------------------------
# Tests: _resolve_single_file_name — three-step precedence
# ---------------------------------------------------------------------------


class TestResolveSingleFileName:
    """Three-step filename precedence: filename > host_path > display_name."""

    def test_filename_from_source_metadata_filename(self) -> None:
        """source_metadata.filename is used first regardless of other fields."""
        # Arrange
        source_metadata = {"filename": "spec.yaml"}

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name="ignored",
            source_metadata=source_metadata,
        )

        # Assert
        assert result == "spec.yaml"

    def test_filename_with_directory_prefix_returns_basename_only(self) -> None:
        """source_metadata.filename with a dir prefix yields only the basename."""
        # Arrange
        source_metadata = {"filename": "/home/user/docs/spec.yaml"}

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name="ignored",
            source_metadata=source_metadata,
        )

        # Assert
        assert result == "spec.yaml"

    def test_host_path_basename_used_when_filename_absent(self) -> None:
        """source_metadata.host_path basename is used when filename is not present."""
        # Arrange
        source_metadata = {"host_path": "/home/user/notes.md"}

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name="ignored",
            source_metadata=source_metadata,
        )

        # Assert
        assert result == "notes.md"

    def test_host_path_with_nested_path_returns_basename_only(self) -> None:
        """host_path with directory prefix returns only the final component."""
        # Arrange
        source_metadata = {"host_path": "/var/data/nested/dir/schema.json"}

        # Act
        result = _resolve_single_file_name(
            resource_type="schema",
            display_name="ignored",
            source_metadata=source_metadata,
        )

        # Assert
        assert result == "schema.json"

    def test_filename_wins_over_host_path_when_both_present(self) -> None:
        """filename takes strict precedence over host_path when both are set."""
        # Arrange
        source_metadata = {
            "filename": "winner.yaml",
            "host_path": "/home/user/loser.md",
        }

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name="ignored",
            source_metadata=source_metadata,
        )

        # Assert
        assert result == "winner.yaml"

    def test_host_path_wins_over_display_name(self) -> None:
        """host_path is used over display_name when filename is absent."""
        # Arrange
        source_metadata = {"host_path": "/var/data/schema.json"}

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name="should be ignored",
            source_metadata=source_metadata,
        )

        # Assert
        assert result == "schema.json"

    def test_display_name_with_existing_extension_returned_unchanged(self) -> None:
        """display_name that already contains an extension is returned as-is."""
        # Arrange
        display_name = "report.pdf"

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name=display_name,
            source_metadata=None,
        )

        # Assert
        assert result == "report.pdf"

    def test_display_name_without_extension_gets_document_default(self) -> None:
        """display_name without extension gets '.md' appended for document type."""
        # Arrange
        display_name = "my report"

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name=display_name,
            source_metadata=None,
        )

        # Assert
        assert result == "my report.md"

    def test_display_name_without_extension_gets_schema_default(self) -> None:
        """display_name without extension gets '.json' appended for schema type."""
        # Arrange
        display_name = "api spec"

        # Act
        result = _resolve_single_file_name(
            resource_type="schema",
            display_name=display_name,
            source_metadata=None,
        )

        # Assert
        assert result == "api spec.json"

    def test_empty_display_name_falls_back_to_document_literal_with_extension(
        self,
    ) -> None:
        """Empty display_name falls back to 'document' plus the type's default extension."""
        # Arrange
        display_name = ""

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name=display_name,
            source_metadata=None,
        )

        # Assert
        assert result == "document.md"

    def test_strips_leading_and_trailing_whitespace_from_display_name(self) -> None:
        """Leading/trailing whitespace in display_name is stripped before use."""
        # Arrange
        display_name = "  report  "

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name=display_name,
            source_metadata=None,
        )

        # Assert
        assert result == "report.md"

    def test_none_source_metadata_treated_as_empty(self) -> None:
        """None source_metadata is safe and falls through to display_name logic."""
        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name="notes",
            source_metadata=None,
        )

        # Assert
        assert result == "notes.md"

    def test_blank_filename_in_metadata_falls_through_to_host_path(self) -> None:
        """A whitespace-only filename is treated as absent; host_path is used next."""
        # Arrange
        source_metadata = {"filename": "   ", "host_path": "/data/target.md"}

        # Act
        result = _resolve_single_file_name(
            resource_type="document",
            display_name="ignored",
            source_metadata=source_metadata,
        )

        # Assert
        assert result == "target.md"


# ---------------------------------------------------------------------------
# Tests: materialize_workspace — on_conflict policy and outcomes
# ---------------------------------------------------------------------------


class TestMaterializeWorkspace:
    """Tests for the on_conflict policy and MaterializeOutcome correctness."""

    def test_empty_bindings_returns_empty_list(self, tmp_path: Path) -> None:
        """Providing no bindings produces an empty outcome list without error."""
        # Arrange
        workdir = tmp_path / "workdir"

        # Act
        outcomes = materialize_workspace(workdir, [])

        # Assert
        assert outcomes == []

    def test_single_document_binding_writes_file_with_correct_content(
        self, tmp_path: Path, make_binding
    ) -> None:
        """A single document binding creates the target file with the blob's content."""
        # Arrange
        workdir = tmp_path / "workdir"
        content = b"# Hello World"
        binding = make_binding(display_name="notes", content=content)

        # Act
        materialize_workspace(workdir, [binding])

        # Assert
        written_file = workdir / "notes.md"
        assert written_file.exists()
        assert written_file.read_bytes() == content

    def test_single_binding_produces_one_outcome(
        self, tmp_path: Path, make_binding
    ) -> None:
        """One binding in the input generates exactly one MaterializeOutcome."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding()

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], MaterializeOutcome)

    def test_outcome_binding_id_matches_input(
        self, tmp_path: Path, make_binding
    ) -> None:
        """The outcome's binding_id is propagated unchanged from the binding dict."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding(binding_id="my-binding-42")

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].binding_id == "my-binding-42"

    def test_outcome_content_hash_matches_input(
        self, tmp_path: Path, make_binding
    ) -> None:
        """The outcome's content_hash reflects the version's stored hash."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding(content_hash="sha256-deadbeef")

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].content_hash == "sha256-deadbeef"

    def test_outcome_files_written_is_one_for_single_blob(
        self, tmp_path: Path, make_binding
    ) -> None:
        """files_written equals the number of blobs materialized (1 for a document)."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding()

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].files_written == 1

    def test_outcome_mode_is_copy_for_copy_binding(
        self, tmp_path: Path, make_binding
    ) -> None:
        """Outcome.mode is 'copy' when materialize_mode='copy'."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding(materialize_mode="copy")

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].mode == "copy"

    # -- on_conflict = "error" -----------------------------------------------

    def test_on_conflict_error_raises_file_exists_error(
        self, tmp_path: Path, make_binding
    ) -> None:
        """on_conflict='error' raises FileExistsError when the target already exists."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "notes.md").write_bytes(b"existing")
        binding = make_binding(display_name="notes", on_conflict="error")

        # Act & Assert
        with pytest.raises(FileExistsError):
            materialize_workspace(workdir, [binding])

    def test_on_conflict_error_message_contains_target_path(
        self, tmp_path: Path, make_binding
    ) -> None:
        """FileExistsError message identifies the conflicting target path."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "notes.md").write_bytes(b"existing")
        binding = make_binding(display_name="notes", on_conflict="error")

        # Act & Assert
        with pytest.raises(FileExistsError, match="notes"):
            materialize_workspace(workdir, [binding])

    # -- on_conflict = "skip" ------------------------------------------------

    def test_on_conflict_skip_returns_skipped_outcome_without_raising(
        self, tmp_path: Path, make_binding
    ) -> None:
        """on_conflict='skip' produces a skipped outcome and does not raise."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        existing_content = b"original"
        (workdir / "notes.md").write_bytes(existing_content)
        binding = make_binding(
            display_name="notes",
            on_conflict="skip",
            content=b"new content",
        )

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert len(outcomes) == 1
        assert outcomes[0].skipped is True

    def test_on_conflict_skip_leaves_existing_file_unchanged(
        self, tmp_path: Path, make_binding
    ) -> None:
        """on_conflict='skip' never modifies the existing file on disk."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        existing_content = b"original"
        target = workdir / "notes.md"
        target.write_bytes(existing_content)
        binding = make_binding(
            display_name="notes",
            on_conflict="skip",
            content=b"should not appear",
        )

        # Act
        materialize_workspace(workdir, [binding])

        # Assert
        assert target.read_bytes() == existing_content

    def test_on_conflict_skip_sets_files_written_to_zero(
        self, tmp_path: Path, make_binding
    ) -> None:
        """Skipped outcome reports files_written=0."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "notes.md").write_bytes(b"existing")
        binding = make_binding(display_name="notes", on_conflict="skip")

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].files_written == 0

    def test_on_conflict_skip_sets_skipped_reason(
        self, tmp_path: Path, make_binding
    ) -> None:
        """Skipped outcome carries a non-empty skipped_reason string."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "notes.md").write_bytes(b"existing")
        binding = make_binding(display_name="notes", on_conflict="skip")

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].skipped_reason is not None
        assert len(outcomes[0].skipped_reason) > 0

    def test_on_conflict_skip_without_conflict_writes_normally(
        self, tmp_path: Path, make_binding
    ) -> None:
        """When the destination does not exist, on_conflict='skip' still writes."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding(
            display_name="fresh",
            on_conflict="skip",
            content=b"brand new",
        )

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].skipped is False
        assert outcomes[0].files_written == 1
        assert (workdir / "fresh.md").read_bytes() == b"brand new"

    # -- on_conflict = "overwrite" -------------------------------------------

    def test_on_conflict_overwrite_replaces_existing_file_content(
        self, tmp_path: Path, make_binding
    ) -> None:
        """on_conflict='overwrite' replaces the existing file with the new blob."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "notes.md").write_bytes(b"old content")
        new_content = b"new content"
        binding = make_binding(
            display_name="notes",
            on_conflict="overwrite",
            content=new_content,
        )

        # Act
        materialize_workspace(workdir, [binding])

        # Assert
        assert (workdir / "notes.md").read_bytes() == new_content

    def test_on_conflict_overwrite_outcome_is_not_skipped(
        self, tmp_path: Path, make_binding
    ) -> None:
        """on_conflict='overwrite' produces a non-skipped outcome."""
        # Arrange
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "notes.md").write_bytes(b"old")
        binding = make_binding(
            display_name="notes",
            on_conflict="overwrite",
            content=b"new",
        )

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert outcomes[0].skipped is False
        assert outcomes[0].files_written == 1

    # -- path resolution and structure ---------------------------------------

    def test_target_path_none_infers_filename_from_display_name(
        self, tmp_path: Path, make_binding
    ) -> None:
        """target_path=None causes the filename to be derived from display_name."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding(
            display_name="readme",
            target_path=None,
            source_metadata=None,
        )

        # Act
        outcomes = materialize_workspace(workdir, [binding])

        # Assert
        assert (workdir / "readme.md").exists()
        assert outcomes[0].target_path == "readme.md"

    def test_target_path_subfolder_creates_nested_file(
        self, tmp_path: Path, make_binding
    ) -> None:
        """Specifying target_path places the file inside that subdirectory."""
        # Arrange
        workdir = tmp_path / "workdir"
        binding = make_binding(
            display_name="spec",
            target_path="docs/api",
            source_metadata={"filename": "openapi.yaml"},
        )

        # Act
        materialize_workspace(workdir, [binding])

        # Assert
        assert (workdir / "docs" / "api" / "openapi.yaml").exists()

    def test_workdir_created_automatically_when_absent(
        self, tmp_path: Path, make_binding
    ) -> None:
        """materialize_workspace creates the workdir if it does not yet exist."""
        # Arrange
        workdir = tmp_path / "new" / "nested" / "workdir"
        binding = make_binding()

        # Act
        materialize_workspace(workdir, [binding])

        # Assert
        assert workdir.is_dir()

    def test_multiple_bindings_produce_one_outcome_each(
        self, tmp_path: Path, make_binding
    ) -> None:
        """Each binding in the input list generates exactly one outcome."""
        # Arrange
        workdir = tmp_path / "workdir"
        bindings = [
            make_binding(
                binding_id="b1",
                display_name="file_one",
                content=b"content one",
            ),
            make_binding(
                binding_id="b2",
                display_name="file_two",
                content=b"content two",
            ),
        ]

        # Act
        outcomes = materialize_workspace(workdir, bindings)

        # Assert
        assert len(outcomes) == 2
        assert {o.binding_id for o in outcomes} == {"b1", "b2"}

    def test_multiple_bindings_all_files_written_to_disk(
        self, tmp_path: Path, make_binding
    ) -> None:
        """All binding files are present on disk after materialize_workspace."""
        # Arrange
        workdir = tmp_path / "workdir"
        bindings = [
            make_binding(
                binding_id="b1",
                display_name="alpha",
                content=b"alpha body",
            ),
            make_binding(
                binding_id="b2",
                display_name="beta",
                content=b"beta body",
            ),
        ]

        # Act
        materialize_workspace(workdir, bindings)

        # Assert
        assert (workdir / "alpha.md").read_bytes() == b"alpha body"
        assert (workdir / "beta.md").read_bytes() == b"beta body"
