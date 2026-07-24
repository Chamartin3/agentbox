"""AgentService (increment 1) — lifecycle + feedback over db managers.

Proves the ported meta/lifecycle/comments/ratings cluster works through
the AgentService surface, with the Database resolved internally (no db
passed in) — pointed at a per-test tmp dir via ``AGENTBOX_DATA_DIR``.
"""
from __future__ import annotations

import json as _json
from pathlib import Path

import pytest

from agentbox.core.db.database import Database
from agentbox.core.db.agents.version import AgentVersionFile
from agentbox.core.service import RunnerSpec
from agentbox.core.service.agents import (
    AgentAlreadyExists,
    AgentNotFound,
    AgentServiceError,
    DuplicateVersionFile,
    VersionFileNotFound,
    VersionNotDraft,
    VersionNotFound,
)
from agentbox.core.service.agents import AgentService

agent_version_files = AgentVersionFile.__table__


def _seed_version(db: Database, agent_id: str = "a1", version: int = 1, vid: int = 1) -> int:
    """Insert one agent_versions row with explicit id; return it."""
    db.agent_versions.create(
        id=vid,
        agent_id=agent_id,
        version=version,
        source_path="mem",
        source_format="inline",
        content_snapshot="{}",
        prompt_snapshot="hi",
        content_hash="deadbeef",
        author="tester",
        created_at="2026-01-01T00:00:00",
    )
    return vid


@pytest.fixture()
def svc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AgentService:
    # tmp_path is unique per test → unique db_path → fresh cached Database.
    monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
    return AgentService()


def test_soft_delete_and_restore(svc: AgentService) -> None:
    _seed_version(svc._db)
    meta = svc.soft_delete("a1")
    assert meta is not None and meta["deleted_at"]
    assert svc.is_deleted("a1") is True
    svc.restore("a1")
    assert svc.is_deleted("a1") is False


def test_disable_and_enable(svc: AgentService) -> None:
    _seed_version(svc._db)
    meta = svc.disable("a1")
    assert meta is not None and meta["disabled_at"]
    assert svc.is_disabled("a1") is True
    svc.enable("a1")
    assert svc.is_disabled("a1") is False


def test_soft_delete_unknown_agent_returns_none(svc: AgentService) -> None:
    assert svc.soft_delete("ghost") is None  # no version history


def test_comments_roundtrip(svc: AgentService) -> None:
    vid = _seed_version(svc._db)
    svc.add_comment(vid, "alice", "looks good")
    svc.add_comment(vid, "bob", "ship it")
    bodies = [c["body"] for c in svc.list_comments(vid)]
    assert bodies == ["looks good", "ship it"]


def test_ratings_roundtrip_and_bounds(svc: AgentService) -> None:
    vid = _seed_version(svc._db)
    svc.set_rating(vid, 4, "alice")
    assert svc.get_rating(vid)["rating"] == 4
    with pytest.raises(ValueError):
        svc.set_rating(vid, 9, "alice")


def test_create_agent_and_duplicate(svc: AgentService) -> None:
    v1 = svc.create_agent("bot", {"model": "x"}, author="alice", changelog="init")
    assert v1["version"] == 1
    assert svc.latest_version("bot")["version"] == 1
    assert svc.active_version("bot") is None  # create does not activate
    with pytest.raises(ValueError):
        svc.create_agent("bot", {"model": "y"}, author="alice", changelog="again")


def test_add_version_appends_and_undeletes(svc: AgentService) -> None:
    svc.create_agent("bot", {"model": "x"}, author="alice", changelog="init")
    svc.soft_delete("bot")
    assert svc.is_deleted("bot") is True
    v2 = svc.add_agent_version("bot", {"model": "y"}, author="bob", changelog="v2")
    assert v2["version"] == 2
    assert svc.is_deleted("bot") is False  # add_version clears deleted_at


def test_publish_activates_and_validates(svc: AgentService) -> None:
    svc.create_agent("bot", {"model": "x"}, author="alice", changelog="init")
    svc.publish_version("bot", 1, "go live")
    active = svc.active_version("bot")
    assert active["version"] == 1
    assert "publish: go live" in active["changelog"]
    with pytest.raises(ValueError):
        svc.publish_version("bot", 1, "no")  # reason too short
    with pytest.raises(ValueError):
        svc.publish_version("bot", 99, "missing version")


def test_rollback_clones_files_and_activates(svc: AgentService) -> None:
    v1 = svc.create_agent("bot", {"model": "x"}, author="alice", changelog="init")
    svc._db.agent_version_files.create(
        id=1,
        version_id=v1["id"],
        relative_path="a.md",
        kind="doc",
        content="hello",
        sha256="abc",
        position=0,
        created_at="2026-01-01T00:00:00",
    )
    svc.add_agent_version("bot", {"model": "y"}, author="bob", changelog="v2")
    new = svc.rollback_to("bot", 1, "back to v1", author="carol")
    assert new["version"] == 3
    assert new["config_json"] == v1["config_json"]  # cloned config
    assert svc.active_version("bot")["version"] == 3  # rollback activates
    # files copied to the new version
    with svc._db.agent_version_files._engine.connect() as conn:
        rows = conn.execute(
            agent_version_files.select().where(
                agent_version_files.c.version_id == new["id"]
            )
        ).fetchall()
    assert len(rows) == 1 and rows[0]._mapping["content"] == "hello"
    with pytest.raises(ValueError):
        svc.rollback_to("bot", 99, "missing target", author="carol")


def test_grant_revoke_reactivate(svc: AgentService) -> None:
    # The agent must exist — agent_tool_grants.agent_id is an enforced FK now.
    svc.create_agent("a1", {"id": "a1"}, author="alice", changelog="init")
    svc.grant_tool("a1", "fs.read", "initial grant", actor="alice")
    assert svc.active_grants("a1") == {"fs.read"}

    svc.revoke_tool("a1", "fs.read", "no longer needed", actor="bob")
    assert svc.active_grants("a1") == set()
    # revoked row preserved for audit
    assert len(svc.list_tool_grants("a1", include_revoked=True)) == 1

    # re-granting reactivates the same row, not a duplicate
    svc.grant_tool("a1", "fs.read", "back again", actor="alice")
    assert svc.active_grants("a1") == {"fs.read"}
    assert len(svc.list_tool_grants("a1", include_revoked=True)) == 1


def test_version_reads(svc: AgentService) -> None:
    _seed_version(svc._db, version=1, vid=1)
    _seed_version(svc._db, version=2, vid=2)
    assert svc.latest_version("a1")["version"] == 2
    assert [v["version"] for v in svc.list_versions("a1")] == [2, 1]
    assert svc.get_version("a1", 1)["id"] == 1
    assert svc.get_version_by_id(2)["version"] == 2
    assert svc.active_version("a1") is None  # no pointer set
    assert svc.latest_version("ghost") is None


def test_grant_validation_and_revoke_missing(svc: AgentService) -> None:
    with pytest.raises(ValueError):
        svc.grant_tool("a1", "fs.read", "no")  # changelog too short
    with pytest.raises(ValueError):
        svc.revoke_tool("a1", "fs.read", "not granted yet")  # no active grant


# ── prompts ────────────────────────────────────────────────────────────
def test_save_prompt_version_and_reads(svc: AgentService) -> None:
    """save_prompt_version writes a version; latest is current."""
    v1 = svc.save_prompt_version("bot", "hello", author="alice")
    assert v1["version"] == 1
    assert "is_draft" not in v1
    # Latest = current.
    assert svc.get_latest_committed_prompt("bot")["content"] == "hello"
    # Save with changed content creates v2.
    v2 = svc.save_prompt_version("bot", "hello v2", author="alice")
    assert v2["version"] == 2 and v2["content"] == "hello v2"
    assert svc.get_latest_committed_prompt("bot")["content"] == "hello v2"
    assert [p["version"] for p in svc.list_prompt_versions("bot")] == [2, 1]
    assert svc.get_prompt_version("bot", 1)["content"] == "hello"
    assert svc.get_prompt_version("bot", 2)["content"] == "hello v2"


def test_save_prompt_version_identical_is_noop(svc: AgentService) -> None:
    """Identical content produces no extra version."""
    v1 = svc.save_prompt_version("bot", "same content")
    v2 = svc.save_prompt_version("bot", "same content")
    assert v1["version"] == v2["version"]
    assert len(svc.list_prompt_versions("bot")) == 1


def test_rollback_prompt(svc: AgentService) -> None:
    svc.save_prompt_version("bot", "v1 content")
    svc.save_prompt_version("bot", "v2 content")
    new = svc.rollback_prompt("bot", 1)
    assert new["content"] == "v1 content"
    assert new["version"] == 3
    assert "is_draft" not in new
    assert "Rollback to version 1" in new["changelog"]
    with pytest.raises(ValueError):
        svc.rollback_prompt("bot", 99)  # missing target


def test_sync_prompt_from_disk(svc: AgentService) -> None:
    first = svc.sync_prompt_from_disk("bot", "disk content")
    assert first is not None and first["changelog"] == "Imported from disk"
    # identical content → no-op
    assert svc.sync_prompt_from_disk("bot", "disk content") is None
    changed = svc.sync_prompt_from_disk("bot", "edited on disk")
    assert changed is not None and changed["changelog"] == "Out-of-band file edit"
    assert changed["version"] == 2


# ── sync metadata ──────────────────────────────────────────────────────
def test_agent_sync_upsert_and_delete(svc: AgentService) -> None:
    assert svc.get_agent_sync("bot") is None
    row = svc.upsert_agent_sync("bot", proxy_path="/tmp/bot")
    assert row["proxy_path"] == "/tmp/bot"
    assert row["sync_mode"] == "manual" and row["sync_policy"] == "db_wins"
    # patch only supplied fields; proxy_path preserved
    row2 = svc.upsert_agent_sync("bot", sync_mode="auto")
    assert row2["sync_mode"] == "auto" and row2["proxy_path"] == "/tmp/bot"
    svc.delete_agent_sync("bot")
    assert svc.get_agent_sync("bot") is None


# ── config events ──────────────────────────────────────────────────────
def test_config_events_record_and_list(svc: AgentService) -> None:
    r = svc.record_config_event("bot", "model", "x", "y", author="alice")
    assert r["from_value"] == '"x"' and r["to_value"] == '"y"'
    svc.record_config_event("bot", "model", "y", "z")
    events = svc.list_config_events("bot")
    assert len(events) == 2
    assert {e["field"] for e in events} == {"model"}


def test_config_event_none_values(svc: AgentService) -> None:
    r = svc.record_config_event("bot", "workspace", None, "ws1")
    assert r["from_value"] is None and r["to_value"] == '"ws1"'


# ── version files ──────────────────────────────────────────────────────
def _files() -> list[dict]:
    return [{"relative_path": "a.md", "content": "aaa", "kind": "system"}]


def test_create_version_with_files_and_list(svc: AgentService) -> None:
    v = svc.create_version(
        "bot", "src", "inline", "{}", "hi", "hash", files=_files()
    )
    assert v["version"] == 1
    files = svc.list_version_files(v["id"])
    assert len(files) == 1 and files[0]["relative_path"] == "a.md"
    assert files[0]["sha256"]  # auto-hashed


def test_version_files_insert_replace_delete(svc: AgentService) -> None:
    v = svc.create_version("bot", "src", "inline", "{}", "hi", "hash")
    svc.insert_version_files(v["id"], _files())
    assert len(svc.list_version_files(v["id"])) == 1
    svc.replace_version_files(
        v["id"], [{"relative_path": "b.md", "content": "bbb"}]
    )
    remaining = svc.list_version_files(v["id"])
    assert len(remaining) == 1 and remaining[0]["relative_path"] == "b.md"
    svc.delete_version_file(remaining[0]["id"])
    assert svc.list_version_files(v["id"]) == []
    svc.insert_version_files(v["id"], _files())
    svc.delete_version_files(v["id"])
    assert svc.list_version_files(v["id"]) == []


def test_create_version_rejects_duplicate_paths(svc: AgentService) -> None:
    dupe = [
        {"relative_path": "a.md", "content": "x"},
        {"relative_path": "a.md", "content": "y"},
    ]
    with pytest.raises(ValueError):
        svc.create_version("bot", "src", "inline", "{}", "hi", "hash", files=dupe)


def test_replace_version_config_and_activate(svc: AgentService) -> None:
    v = svc.create_version("bot", "src", "inline", "{}", "hi", "hash")
    svc.replace_version_config(v["id"], '{"model": "z"}')
    assert svc.get_version_by_id(v["id"])["config_json"] == '{"model": "z"}'
    svc.activate_version("bot", v["id"])
    assert svc.active_version("bot")["id"] == v["id"]


# ── revisions ──────────────────────────────────────────────────────────
def test_branch_draft(svc: AgentService) -> None:
    v1 = svc.create_version(
        "bot", "src", "inline", "{}", "hi", "h", config_json='{"id": "bot"}'
    )
    svc.activate_version("bot", v1["id"])
    branch = svc.branch_draft("bot", author="alice")
    assert branch["version"] == 2
    assert "branched from v1" in branch["changelog"]
    # branch does not activate
    assert svc.active_version("bot")["version"] == 1
    with pytest.raises(ValueError):
        svc.branch_draft("ghost", author="alice")


def test_save_prompt_revision_activates(svc: AgentService) -> None:
    v1 = svc.create_version(
        "bot", "src", "inline", "{}", "hi", "h", config_json='{"id": "bot"}'
    )
    svc.activate_version("bot", v1["id"])
    rev = svc.save_prompt_revision(
        "bot", prompt_content="new prompt", author="alice", activate=True
    )
    assert rev["version"] == 2 and rev["prompt_content"] == "new prompt"
    assert '"prompt": "new prompt"' in rev["config_json"]
    assert svc.active_version("bot")["version"] == 2
    with pytest.raises(ValueError):
        svc.save_prompt_revision("ghost", prompt_content="x", author="a")


def test_save_config_revision_merges(svc: AgentService) -> None:
    v1 = svc.create_version(
        "bot", "src", "inline", "{}", "hi", "h",
        config_json='{"id": "bot", "model": "a"}',
    )
    svc.activate_version("bot", v1["id"])
    rev = svc.save_config_revision(
        "bot", config_patch={"model": "b"}, author="alice"
    )
    cfg = _json.loads(rev["config_json"])
    assert cfg["model"] == "b" and cfg["id"] == "bot"
    assert svc.active_version("bot")["version"] == 2  # activate defaults True


# ── resolution reads ───────────────────────────────────────────────────
def test_list_agents_with_latest_filters(svc: AgentService) -> None:
    svc.create_agent("a", {"id": "a"}, author="x", changelog="init")
    svc.create_agent("b", {"id": "b"}, author="x", changelog="init")
    svc.soft_delete("a")
    svc.disable("b")
    ids = {r["agent_id"] for r in svc.list_agents_with_latest()}
    assert ids == set()  # both hidden
    ids_deleted = {r["agent_id"] for r in svc.list_agents_with_latest(include_deleted=True)}
    assert ids_deleted == {"a"}
    ids_all = {
        r["agent_id"]
        for r in svc.list_agents_with_latest(include_deleted=True, include_disabled=True)
    }
    assert ids_all == {"a", "b"}


def test_get_agent_def(svc: AgentService) -> None:
    v1 = svc.create_agent("bot", {"id": "bot", "description": "d"}, author="x", changelog="i")
    svc.activate_version("bot", v1["id"])
    agent_def = svc.get_agent_def("bot")
    assert agent_def is not None and agent_def.id == "bot"
    assert svc.get_agent_def("ghost") is None
    svc.soft_delete("bot")
    assert svc.get_agent_def("bot") is None  # deleted → None


# ── Category-B absorbed methods ────────────────────────────────────────


def _activate_bot(svc: AgentService, agent_id: str = "bot") -> None:
    v1 = svc.create_agent(
        agent_id, {"id": agent_id, "description": "d"}, author="x", changelog="i"
    )
    svc.activate_version(agent_id, v1["id"])


def test_resolve_agent_and_require_exists(svc: AgentService) -> None:
    _activate_bot(svc)
    assert svc.resolve_agent("bot") is not None
    assert svc.resolve_agent("ghost") is None
    svc.require_agent_exists("bot")  # no raise
    with pytest.raises(AgentNotFound):
        svc.require_agent_exists("ghost")


def test_list_all_agents(svc: AgentService) -> None:
    _activate_bot(svc, "bot")
    _activate_bot(svc, "bot2")
    ids = {a.id for a in svc.list_all_agents()}
    assert ids == {"bot", "bot2"}


def test_create_agent_record_and_duplicate(svc: AgentService) -> None:
    kwargs = dict(
        agent_id="made",
        description="via record",
        runner=RunnerSpec(),
        prompt="hello",
        composition=None,
        tools=None,
        tags=["t1"],
        workspace=None,
        session_mode=None,
        webhook_url=None,
        author="tester",
        changelog="init",
    )
    rec = svc.create_agent_record(**kwargs)
    assert rec["version"] == 1
    with pytest.raises(AgentAlreadyExists):
        svc.create_agent_record(**kwargs)


def test_create_agent_record_reversions_deleted(svc: AgentService) -> None:
    kwargs = dict(
        agent_id="rev",
        description="d",
        runner=RunnerSpec(),
        prompt="p",
        composition=None,
        tools=None,
        tags=None,
        workspace=None,
        session_mode=None,
        webhook_url=None,
        author="tester",
        changelog="init",
    )
    svc.create_agent_record(**kwargs)
    svc.soft_delete("rev")
    rec2 = svc.create_agent_record(**kwargs)  # re-version, not error
    assert rec2["version"] == 2


def test_upload_and_remove_version_file(svc: AgentService) -> None:
    v = svc.create_agent("f", {"id": "f"}, author="x", changelog="i")  # draft (no active)
    res = svc.upload_version_file(
        agent_id="f", version=v["version"], kind="reference", name="a.md", content="x"
    )
    fid = res["file"]["id"]
    assert res["size"] == 1
    # duplicate content → DuplicateVersionFile
    with pytest.raises(DuplicateVersionFile):
        svc.upload_version_file(
            agent_id="f", version=v["version"], kind="reference", name="b.md", content="x"
        )
    with pytest.raises(VersionNotFound):
        svc.upload_version_file(
            agent_id="f", version=99, kind="reference", name="c.md", content="z"
        )
    svc.remove_version_file(agent_id="f", version=v["version"], file_id=fid)
    assert svc.list_version_files(v["id"]) == []
    with pytest.raises(VersionFileNotFound):
        svc.remove_version_file(agent_id="f", version=v["version"], file_id=fid)


def test_upload_version_file_rejects_active(svc: AgentService) -> None:
    v = svc.create_agent("g", {"id": "g"}, author="x", changelog="i")
    svc.activate_version("g", v["id"])
    with pytest.raises(VersionNotDraft):
        svc.upload_version_file(
            agent_id="g", version=v["version"], kind="reference", name="a.md", content="x"
        )


def test_update_agent_meta_alias(svc: AgentService) -> None:
    svc.create_agent("a1", {"id": "a1"}, author="x", changelog="i")  # creates meta row
    out = svc.update_agent_meta("a1", sync_mode="manual", export_to_disk=True)
    assert out is not None and out["sync_mode"] == "manual"


def test_decode_config_json(svc: AgentService) -> None:
    assert svc.decode_config_json('{"a": 1}') == {"a": 1}
    assert svc.decode_config_json({"b": 2}) == {"b": 2}
    assert svc.decode_config_json(None) == {}
    assert svc.decode_config_json("not json") == {}


def test_normalize_validator_entries(svc: AgentService) -> None:
    out = svc.normalize_validator_entries(
        "output", [{"kind": "http", "endpoint": "http://x"}]
    )
    assert out[0]["kind"] == "http" and out[0]["endpoint"] == "http://x"
    with pytest.raises(AgentServiceError):
        svc.normalize_validator_entries("output", [{"kind": "http"}])  # missing endpoint


def test_get_agent_validation_reads_inline(svc: AgentService) -> None:
    cfg = _json.dumps(
        {"output": {"validators": [{"kind": "http", "endpoint": "http://x"}]}}
    )
    v = svc.create_agent("val", {"id": "val"}, author="x", changelog="i")
    svc.replace_version_config(v["id"], cfg)
    svc.activate_version("val", v["id"])
    got = svc.get_agent_validation("val")
    assert got["agent_version_id"] == v["id"]
    assert got["output"]["validators"][0]["endpoint"] == "http://x"
    assert got["input"] is None


def test_get_agent_validation_no_active(svc: AgentService) -> None:
    got = svc.get_agent_validation("nobody")
    assert got == {
        "agent_id": "nobody",
        "agent_version_id": None,
        "input": None,
        "output": None,
    }


def test_create_version_from_snapshot_resolves_and_appends(svc: AgentService) -> None:
    v1 = svc.create_agent("bot", {"id": "bot", "description": "d"}, author="alice", changelog="init")
    svc.activate_version("bot", v1["id"])

    row = svc.create_version_from_snapshot(
        "bot", '{"id": "bot"}', author="bob", changelog="snap"
    )

    assert row["agent_id"] == "bot"
    assert row["version"] == 2  # create_agent seeded v1
    assert row["changelog"] == "snap"


def test_create_version_from_snapshot_unknown_agent_raises(svc: AgentService) -> None:
    with pytest.raises(AgentNotFound):
        svc.create_version_from_snapshot("ghost", "{}")
