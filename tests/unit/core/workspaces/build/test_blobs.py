"""Unit tests for core/workspaces/generation/blobs.py — materialize_blobs."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentbox.core.workspaces.build.bindings import materialize_blobs


# ---------------------------------------------------------------------------
# Document mode — single blob with relative_path == ""
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMaterializeBlobsDocumentMode:
    """materialize_blobs: single blob whose relative_path is empty (document mode).

    In this mode target_root IS the file being written; callers name the
    destination explicitly.
    """

    def test_single_doc_writes_to_target_root(
        self, tmp_path: Path, single_doc_blob
    ) -> None:
        """A single document blob writes its content to target_root itself."""
        # Arrange
        target = tmp_path / "target" / "spec.yaml"
        blobs = single_doc_blob(content=b"key: value\n")

        # Act
        materialize_blobs(blobs, target)

        # Assert
        assert target.exists()
        assert target.read_bytes() == b"key: value\n"

    def test_single_doc_creates_parent_dirs(
        self, tmp_path: Path, single_doc_blob
    ) -> None:
        """Parent directories are created automatically when they do not exist."""
        # Arrange
        target = tmp_path / "a" / "b" / "c" / "doc.md"
        blobs = single_doc_blob(content=b"# heading")

        # Act
        materialize_blobs(blobs, target)

        # Assert
        assert target.is_file()
        assert target.read_bytes() == b"# heading"

    def test_single_doc_returns_written_path(
        self, tmp_path: Path, single_doc_blob
    ) -> None:
        """Return value is a list containing exactly the target_root path."""
        # Arrange
        target = tmp_path / "output.txt"
        blobs = single_doc_blob()

        # Act
        written = materialize_blobs(blobs, target)

        # Assert
        assert written == [target]

    def test_single_doc_overwrites_existing_file(
        self, tmp_path: Path, single_doc_blob
    ) -> None:
        """With overwrite=True (default), an existing file is replaced."""
        # Arrange
        target = tmp_path / "notes.txt"
        target.write_bytes(b"old content")
        blobs = single_doc_blob(content=b"new content")

        # Act
        written = materialize_blobs(blobs, target, overwrite=True)

        # Assert
        assert written == [target]
        assert target.read_bytes() == b"new content"

    def test_single_doc_skips_when_overwrite_false(
        self, tmp_path: Path, single_doc_blob
    ) -> None:
        """With overwrite=False, an existing file is left unchanged and [] is returned."""
        # Arrange
        target = tmp_path / "notes.txt"
        original = b"original content"
        target.write_bytes(original)
        blobs = single_doc_blob(content=b"replacement")

        # Act
        written = materialize_blobs(blobs, target, overwrite=False)

        # Assert
        assert written == []
        assert target.read_bytes() == original

    def test_single_doc_removes_existing_dir_before_write(
        self, tmp_path: Path, single_doc_blob
    ) -> None:
        """When target_root is a directory (from prior folder materialization) it is
        removed and replaced by the document file."""
        # Arrange
        target = tmp_path / "resource"
        # Simulate a prior folder-mode materialization that left a directory there.
        target.mkdir()
        (target / "old_blob.py").write_bytes(b"stale")
        blobs = single_doc_blob(content=b"document body")

        # Act
        written = materialize_blobs(blobs, target, overwrite=True)

        # Assert
        assert written == [target]
        assert target.is_file()
        assert target.read_bytes() == b"document body"


# ---------------------------------------------------------------------------
# Folder / skill mode — multiple blobs or non-empty relative_paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMaterializeBlobsFolderMode:
    """materialize_blobs: multiple blobs or blobs with non-empty relative_paths.

    In this mode target_root becomes a directory; each blob's relative_path
    names a file within it.
    """

    def test_folder_writes_all_blobs(self, tmp_path: Path, make_blob) -> None:
        """All blobs in a folder set are written under target_root."""
        # Arrange
        target = tmp_path / "skill"
        blobs = [
            make_blob("main.py", b"print('hello')"),
            make_blob("utils/helper.py", b"def help(): pass"),
            make_blob("README.md", b"# Skill"),
        ]

        # Act
        materialize_blobs(blobs, target)

        # Assert
        assert (target / "main.py").read_bytes() == b"print('hello')"
        assert (target / "utils" / "helper.py").read_bytes() == b"def help(): pass"
        assert (target / "README.md").read_bytes() == b"# Skill"

    def test_folder_creates_target_dir(self, tmp_path: Path, folder_blobs) -> None:
        """target_root is created as a directory when it does not exist."""
        # Arrange
        target = tmp_path / "brand_new_dir"
        blobs = folder_blobs("file.txt")

        # Act
        materialize_blobs(blobs, target)

        # Assert
        assert target.is_dir()

    def test_folder_skips_empty_rel_path_blob(
        self, tmp_path: Path, make_blob
    ) -> None:
        """A blob with relative_path='' inside a folder set is skipped silently.

        This is a defensive guard — a folder resource version should never
        include such an entry, but the materializer must not overwrite the
        directory itself if it does.
        """
        # Arrange
        target = tmp_path / "skill"
        # Two valid blobs plus one rogue empty-rel-path blob.
        blobs = [
            make_blob("a.py", b"# a"),
            make_blob("", b"SHOULD BE IGNORED"),
            make_blob("b.py", b"# b"),
        ]

        # Act
        written = materialize_blobs(blobs, target)

        # Assert
        assert target.is_dir(), "target_root should remain a directory"
        assert set(written) == {target / "a.py", target / "b.py"}
        assert (target / "a.py").read_bytes() == b"# a"
        assert (target / "b.py").read_bytes() == b"# b"

    def test_folder_overwrites_existing_files(
        self, tmp_path: Path, make_blob
    ) -> None:
        """With overwrite=True, existing files under target_root are replaced."""
        # Arrange
        target = tmp_path / "skill"
        target.mkdir()
        (target / "config.json").write_bytes(b'{"old": true}')
        blobs = [make_blob("config.json", b'{"new": true}')]

        # Act
        written = materialize_blobs(blobs, target, overwrite=True)

        # Assert
        assert written == [target / "config.json"]
        assert (target / "config.json").read_bytes() == b'{"new": true}'

    def test_folder_skips_existing_when_overwrite_false(
        self, tmp_path: Path, make_blob
    ) -> None:
        """With overwrite=False, already-present files are not touched and nothing
        is appended to the returned list."""
        # Arrange
        target = tmp_path / "skill"
        target.mkdir()
        (target / "existing.py").write_bytes(b"original")
        blobs = [make_blob("existing.py", b"replacement")]

        # Act
        written = materialize_blobs(blobs, target, overwrite=False)

        # Assert
        assert written == []
        assert (target / "existing.py").read_bytes() == b"original"

    def test_folder_removes_file_obstacle_before_writing(
        self, tmp_path: Path, folder_blobs
    ) -> None:
        """When target_root is a plain file (prior document materialization),
        it is removed and replaced by a directory so folder blobs can be written."""
        # Arrange
        target = tmp_path / "resource"
        # Simulate a prior doc-mode run that left a file at this path.
        target.write_bytes(b"stale document")
        blobs = folder_blobs("module.py")

        # Act
        materialize_blobs(blobs, target, overwrite=True)

        # Assert
        assert target.is_dir()
        assert (target / "module.py").is_file()

    def test_folder_preserves_unrelated_files(
        self, tmp_path: Path, make_blob
    ) -> None:
        """Files already present under target_root that are not named in the
        current blob set are left intact."""
        # Arrange
        target = tmp_path / "skill"
        target.mkdir()
        unrelated = target / "unrelated.txt"
        unrelated.write_bytes(b"keep me")
        blobs = [make_blob("new_file.py", b"# new")]

        # Act
        materialize_blobs(blobs, target)

        # Assert
        assert unrelated.read_bytes() == b"keep me"
        assert (target / "new_file.py").read_bytes() == b"# new"

    def test_folder_returns_all_written_paths(
        self, tmp_path: Path, make_blob
    ) -> None:
        """Return value contains every path actually written in this call."""
        # Arrange
        target = tmp_path / "skill"
        blobs = [
            make_blob("alpha.py", b"# alpha"),
            make_blob("beta.py", b"# beta"),
        ]

        # Act
        written = materialize_blobs(blobs, target)

        # Assert
        assert set(written) == {target / "alpha.py", target / "beta.py"}

    def test_folder_file_obstacle_overwrite_false_returns_empty(
        self, tmp_path: Path, folder_blobs
    ) -> None:
        """When target_root is a file and overwrite=False the whole call is a
        no-op and [] is returned without touching the filesystem."""
        # Arrange
        target = tmp_path / "resource"
        target.write_bytes(b"existing file content")
        blobs = folder_blobs("blob.py")

        # Act
        written = materialize_blobs(blobs, target, overwrite=False)

        # Assert
        assert written == []
        assert target.is_file(), "original file must remain untouched"
        assert target.read_bytes() == b"existing file content"
