"""Parity tests for FilesystemBundleSource vs DbBundleSource.

A DB-backed bundle must produce the same ComposeResult as the disk bundle
it was snapshotted from. If this drifts, rolling back a published version
in the DB no longer reproduces the run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from agentbox.composition import ComposeResult, compose_from_source
from agentbox.core.composition.sources import (
    DbBundleSource,
    FilesystemBundleSource,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture
def bundle_on_disk(tmp_path: Path) -> tuple[Path, Path, dict]:
    """A fully-featured bundle with system + user_template + 2 refs + schema."""
    bundle = tmp_path / "agent"
    shared_root = tmp_path / "shared_pool"
    _write(bundle / "prompts/system.md", "SYS {name}\n")
    _write(bundle / "prompts/user.md", "USR {user_message}\n")
    _write(bundle / "refs/local.md", "Local reference body")
    _write(shared_root / "guidelines/rules.md", "Always cite sources.")
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    _write(bundle / "output_schema.json", json.dumps(schema))
    composition = {
        "system": "prompts/system.md",
        "user_template": "prompts/user.md",
        "output_schema": "output_schema.json",
        "references": [
            {"path": "refs/local.md", "heading": "Local"},
            {"path": "shared://guidelines/rules.md", "heading": "Rules"},
        ],
    }
    return bundle, shared_root, composition


@pytest.fixture
def filesystem_source(bundle_on_disk) -> FilesystemBundleSource:
    bundle, shared_root, composition = bundle_on_disk
    return FilesystemBundleSource(
        bundle_path=bundle,
        composition=composition,
        shared_roots={"guidelines": shared_root / "guidelines"},
    )


def _make_db_source_from(fs: FilesystemBundleSource) -> DbBundleSource:
    """Snapshot a FilesystemBundleSource into a DbBundleSource."""
    files: list[dict] = []
    # system
    sys_text = fs.read_system()
    files.append(
        {
            "kind": "system",
            "relative_path": fs.composition["system"],
            "content": sys_text,
            "sha256": _sha(sys_text),
            "source_uri": None,
            "position": 0,
        }
    )
    # user_template
    ut = fs.read_user_template()
    if ut is not None:
        files.append(
            {
                "kind": "user_template",
                "relative_path": fs.composition["user_template"],
                "content": ut,
                "sha256": _sha(ut),
                "source_uri": None,
                "position": 0,
            }
        )
    # references
    for i, ref in enumerate(fs.references()):
        content = fs.read_reference(ref)
        files.append(
            {
                "kind": "reference",
                "relative_path": ref.path,
                "content": content,
                "sha256": _sha(content),
                "source_uri": ref.path if ref.path.startswith("shared://") else None,
                "position": i,
            }
        )
    # output_schema — preserve insertion order so a snapshotted DB
    # bundle reparses into the same dict shape as the disk source.
    info = fs.read_output_schema()
    if info is not None:
        content = json.dumps(info.schema)
        files.append(
            {
                "kind": "output_schema",
                "relative_path": info.relative_path,
                "content": content,
                "sha256": _sha(content),
                "source_uri": None,
                "position": 0,
            }
        )
    return DbBundleSource(composition=dict(fs.composition), files=files)


class TestBundleSourceParity:
    def test_compose_result_matches(self, filesystem_source) -> None:
        db = _make_db_source_from(filesystem_source)
        variables = {"name": "Alice", "user_message": "Hello?"}
        r_fs = compose_from_source(filesystem_source, variables)
        r_db = compose_from_source(db, variables)
        assert isinstance(r_fs, ComposeResult)
        assert isinstance(r_db, ComposeResult)
        assert r_fs.system == r_db.system
        assert r_fs.user == r_db.user
        assert r_fs.schema == r_db.schema
        assert r_fs.schema_sha == r_db.schema_sha

    def test_db_source_reproduces_after_disk_wiped(
        self, filesystem_source, tmp_path
    ) -> None:
        """Snapshot, then nuke the bundle dir — DB source still composes."""
        db = _make_db_source_from(filesystem_source)
        # Wipe the disk bundle entirely.
        import shutil

        shutil.rmtree(filesystem_source.bundle_path)
        # FilesystemBundleSource would now blow up
        with pytest.raises(FileNotFoundError):
            compose_from_source(
                filesystem_source, {"name": "x", "user_message": "y"}
            )
        # DbBundleSource still works
        r = compose_from_source(db, {"name": "x", "user_message": "y"})
        assert "SYS x" in r.system
        assert "USR y" in r.user
        assert r.schema is not None
        assert r.schema["type"] == "object"

    def test_db_source_references_in_order(self, filesystem_source) -> None:
        db = _make_db_source_from(filesystem_source)
        r = compose_from_source(
            db, {"name": "x", "user_message": "y"}
        )
        local_idx = r.system.find("## Local")
        rules_idx = r.system.find("## Rules")
        assert local_idx != -1 and rules_idx != -1
        assert local_idx < rules_idx
