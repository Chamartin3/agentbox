"""Tests for ZipUploadImporter."""

from __future__ import annotations

import io
import zipfile

import pytest
from agentbox.core.resource.importers.base import ImporterContext
from agentbox.core.resource.importers.zip_upload import ZipUploadImporter


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_folder_zip_extracts_blobs():
    payload = _make_zip({"docs/a.txt": b"alpha", "docs/b.txt": b"beta"})
    result = ZipUploadImporter(filename="x.zip", content=payload).run(ImporterContext())
    rel_paths = sorted(b[0] for b in result.blobs)
    assert rel_paths == ["a.txt", "b.txt"]
    assert result.suggested_type == "folder"


def test_skill_zip_requires_skill_md():
    payload = _make_zip(
        {
            "myskill/SKILL.md": b"---\nname: myskill\ndescription: x\n---\nbody",
            "myskill/helper.py": b"x = 1\n",
        }
    )
    result = ZipUploadImporter(filename="s.zip", content=payload, as_skill=True).run(
        ImporterContext()
    )
    assert result.suggested_type == "skill"
    assert result.metadata is not None
    assert result.metadata["skill_name"] == "myskill"


def test_zip_slip_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.txt", b"nope")
    with pytest.raises(ValueError, match="Unsafe zip member"):
        ZipUploadImporter(filename="bad.zip", content=buf.getvalue()).run(
            ImporterContext()
        )


def test_bad_zip_rejected():
    with pytest.raises(ValueError, match="Not a valid zip"):
        ZipUploadImporter(filename="x.zip", content=b"not-a-zip").run(ImporterContext())
