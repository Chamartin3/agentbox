"""target_path semantic: folder destination + filename resolved from source."""

from __future__ import annotations

from pathlib import Path

from agentbox.core.workspaces.build.bindings import (
    _resolve_single_file_name,
    _resolve_target_path,
    materialize_workspace,
)


def _doc_binding(
    *,
    target_path: str | None,
    display_name: str,
    filename: str | None = None,
    content: bytes = b"x",
    resource_type: str = "document",
) -> dict:
    meta = {"filename": filename} if filename else {}
    return {
        "binding_id": "b1",
        "resource_id": "r1",
        "version_id": "v1",
        "content_hash": "h1",
        "type": resource_type,
        "display_name": display_name,
        "target_path": target_path,
        "materialize_mode": "copy",
        "on_conflict": "overwrite",
        "source_metadata": meta,
        "blobs": [{"relative_path": "", "content": content}],
        "skill_meta": None,
    }


def test_filename_from_source_metadata_takes_precedence() -> None:
    name = _resolve_single_file_name(
        resource_type="document",
        display_name="Voice Guidelines",
        source_metadata={"filename": "voice.md"},
    )
    assert name == "voice.md"


def test_filename_from_host_path_fallback() -> None:
    name = _resolve_single_file_name(
        resource_type="document",
        display_name="ignored",
        source_metadata={"host_path": "/var/data/spec.txt"},
    )
    assert name == "spec.txt"


def test_filename_uses_display_name_extension_when_present() -> None:
    name = _resolve_single_file_name(
        resource_type="document",
        display_name="voice.md",
        source_metadata=None,
    )
    assert name == "voice.md"


def test_filename_appends_type_extension_when_missing() -> None:
    assert (
        _resolve_single_file_name(
            resource_type="document", display_name="Voice", source_metadata=None
        )
        == "Voice.md"
    )
    assert (
        _resolve_single_file_name(
            resource_type="schema", display_name="config", source_metadata=None
        )
        == "config.json"
    )


def test_target_path_folder_semantic_for_documents() -> None:
    """target_path = 'docs' + document → 'docs/<filename>'."""
    b = _doc_binding(target_path="docs", display_name="Voice", filename="voice.md")
    assert _resolve_target_path(b) == "docs/voice.md"


def test_target_path_null_drops_at_workspace_root() -> None:
    b = _doc_binding(target_path=None, display_name="Voice", filename="voice.md")
    assert _resolve_target_path(b) == "voice.md"


def test_target_path_folder_for_folder_type_stays_as_directory() -> None:
    """target_path for folder type is the folder itself (legacy semantic)."""
    b = {
        "type": "folder",
        "display_name": "ignored",
        "target_path": "shared",
        "skill_meta": None,
    }
    assert _resolve_target_path(b) == "shared"


def test_materialize_document_lands_at_resolved_filename(tmp_path: Path) -> None:
    """End-to-end: a document with target_path='docs' and filename='voice.md'
    materializes to <workdir>/docs/voice.md, not <workdir>/docs."""
    b = _doc_binding(
        target_path="docs",
        display_name="Voice",
        filename="voice.md",
        content=b"# Voice\n",
    )
    outcomes = materialize_workspace(tmp_path, [b])
    assert len(outcomes) == 1
    expected = tmp_path / "docs" / "voice.md"
    assert expected.exists()
    assert expected.read_text() == "# Voice\n"
    # target_path on the outcome reflects the resolved path
    assert outcomes[0].target_path == "docs/voice.md"


def test_materialize_document_null_target_lands_at_root(tmp_path: Path) -> None:
    b = _doc_binding(
        target_path=None,
        display_name="readme",
        filename="README.md",
        content=b"hi",
    )
    materialize_workspace(tmp_path, [b])
    assert (tmp_path / "README.md").read_text() == "hi"
