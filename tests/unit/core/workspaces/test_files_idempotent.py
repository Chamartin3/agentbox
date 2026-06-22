"""Tests that [[workspaces.files]] re-copy is idempotent and reflects source changes."""

from __future__ import annotations

from pathlib import Path


def _materialize_files(
    target_dir: Path,
    files: list[dict],
    project_root: Path,
) -> None:
    from agentbox.core.workspaces.generation.workspace_files import materialize_workspace_files

    materialize_workspace_files(target_dir, files, project_root)


class TestWorkspaceFilesIdempotent:
    def test_copy_creates_dest_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "data.txt"
        src.parent.mkdir(parents=True)
        src.write_text("hello", encoding="utf-8")

        dst = tmp_path / "run" / "data.txt"
        dst.parent.mkdir(parents=True)

        _materialize_files(
            dst.parent,
            [{"src": "src/data.txt", "dst": "data.txt"}],
            tmp_path,
        )

        assert dst.read_text(encoding="utf-8") == "hello"

    def test_re_copy_is_idempotent_when_source_unchanged(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "data.txt"
        src.parent.mkdir(parents=True)
        src.write_text("unchanged", encoding="utf-8")

        run_dir = tmp_path / "run"
        run_dir.mkdir()

        spec = [{"src": "src/data.txt", "dst": "data.txt"}]

        _materialize_files(run_dir, spec, tmp_path)
        _materialize_files(run_dir, spec, tmp_path)

        assert (run_dir / "data.txt").read_text(encoding="utf-8") == "unchanged"

    def test_re_copy_reflects_source_change(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "data.txt"
        src.parent.mkdir(parents=True)
        src.write_text("v1", encoding="utf-8")

        run_dir = tmp_path / "run"
        run_dir.mkdir()

        spec = [{"src": "src/data.txt", "dst": "data.txt"}]

        _materialize_files(run_dir, spec, tmp_path)
        assert (run_dir / "data.txt").read_text(encoding="utf-8") == "v1"

        src.write_text("v2", encoding="utf-8")
        _materialize_files(run_dir, spec, tmp_path)
        assert (run_dir / "data.txt").read_text(encoding="utf-8") == "v2"

    def test_missing_src_raises_file_not_found(self, tmp_path: Path) -> None:
        import pytest

        run_dir = tmp_path / "run"
        run_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="source does not exist"):
            _materialize_files(
                run_dir,
                [{"src": "nonexistent.txt", "dst": "data.txt"}],
                tmp_path,
            )
