"""Tests for resource blob → prompt-text renderers."""

from __future__ import annotations

import pytest

from agentbox.core.agents.prompt.rendering import (
    _blob_text,
    render_document,
    render_folder_manifest,
    render_for_type,
    render_schema,
    render_script,
    render_skill_primer,
)


class TestBlobText:
    def test_content_text_takes_priority(self) -> None:
        blob = {"content_text": "hello", "content": "ignored"}
        assert _blob_text(blob) == "hello"

    def test_string_content(self) -> None:
        assert _blob_text({"content": "world"}) == "world"

    def test_bytes_content_utf8(self) -> None:
        assert _blob_text({"content": b"bytes"}) == "bytes"

    def test_bytes_content_invalid_utf8_returns_empty(self) -> None:
        assert _blob_text({"content": b"\xff\xfe"}) == ""

    def test_none_content_returns_empty(self) -> None:
        assert _blob_text({}) == ""

    def test_non_string_non_bytes_returns_empty(self) -> None:
        assert _blob_text({"content": 42}) == ""


class TestRenderDocument:
    def test_single_blob(self) -> None:
        result = render_document([{"content": "doc text"}])
        assert result["text"] == "doc text"
        assert result["metadata"]["role"] == "document"

    def test_empty_blobs(self) -> None:
        result = render_document([])
        assert result["text"] == ""
        assert result["metadata"]["role"] == "document"


class TestRenderFolderManifest:
    def test_sorts_paths(self) -> None:
        result = render_folder_manifest([
            {"relative_path": "b.txt"},
            {"relative_path": "a.txt"},
        ])
        lines = result["text"].split("\n")
        assert lines[0] == "- a.txt"
        assert lines[1] == "- b.txt"
        assert result["metadata"]["file_count"] == 2

    def test_skips_missing_relative_path(self) -> None:
        result = render_folder_manifest([
            {"relative_path": "x"},
            {"other": True},
        ])
        assert result["text"] == "- x"
        assert result["metadata"]["file_count"] == 1

    def test_empty_blobs(self) -> None:
        result = render_folder_manifest([])
        assert result["text"] == ""
        assert result["metadata"]["file_count"] == 0


class TestRenderSkillPrimer:
    def test_extracts_skill_md(self) -> None:
        result = render_skill_primer([
            {"relative_path": "SKILL.md", "content": "skill body"},
            {"relative_path": "helper.py", "content": "code"},
        ])
        assert result["text"] == "skill body"
        assert result["metadata"]["entry_path"] == "SKILL.md"
        assert result["metadata"]["file_count"] == 2

    def test_missing_entry(self) -> None:
        result = render_skill_primer([
            {"relative_path": "other.md", "content": "other"},
        ])
        assert result["text"] == ""
        assert result["metadata"]["missing_entry"] is True


class TestRenderSchema:
    def test_renders_first_blob(self) -> None:
        result = render_schema([{"content": '{"type": "object"}'}])
        assert result["text"] == '{"type": "object"}'
        assert result["metadata"]["role"] == "schema"


class TestRenderScript:
    def test_renders_first_blob(self) -> None:
        result = render_script([{"content": "#!/usr/bin/env python3"}])
        assert result["text"] == "#!/usr/bin/env python3"
        assert result["metadata"]["role"] == "script"


class TestRenderForType:
    def test_document(self) -> None:
        result = render_for_type("document", [{"content": "x"}])
        assert result["metadata"]["role"] == "document"

    def test_folder(self) -> None:
        result = render_for_type("folder", [{"relative_path": "f.txt"}])
        assert result["metadata"]["role"] == "folder_manifest"

    def test_skill(self) -> None:
        result = render_for_type("skill", [{"relative_path": "SKILL.md", "content": "s"}])
        assert result["metadata"]["role"] == "skill_primer"

    def test_schema(self) -> None:
        result = render_for_type("schema", [{"content": "{}"}])
        assert result["metadata"]["role"] == "schema"

    def test_script(self) -> None:
        result = render_for_type("script", [{"content": "print(1)"}])
        assert result["metadata"]["role"] == "script"

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown resource type"):
            render_for_type("unknown", [{"content": "x"}])
