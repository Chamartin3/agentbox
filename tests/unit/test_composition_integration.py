"""Tests for prompt-composition integration."""

from __future__ import annotations

import json
from pathlib import Path


class TestCompositionStore:
    def test_save_run_composition(self, tmp_path: Path) -> None:
        from agentbox.core.data.store import SessionStore

        store = SessionStore(tmp_path / "db.sqlite")
        rid = store.create_run(
            agent_id="a1",
            input_="hello",
            workdir="/tmp",
            transcript_path="/tmp/t.jsonl",
        )
        store.save_run_composition(
            run_id=rid,
            composition_snapshot={"bundle_sha": "abc123"},
            rendered_prompt={"system": "sys", "user": "usr", "schema": None},
            variables={"x": "1"},
        )
        rec = store.get_run(rid)
        assert rec is not None
        assert rec.composition_snapshot is not None
        snap = json.loads(rec.composition_snapshot)
        assert snap["bundle_sha"] == "abc123"
        assert rec.rendered_prompt is not None
        assert json.loads(rec.rendered_prompt)["system"] == "sys"
        assert rec.variables is not None
        assert json.loads(rec.variables)["x"] == "1"

    def test_save_run_snapshot(self, tmp_path: Path) -> None:
        from agentbox.core.data.store import SessionStore

        store = SessionStore(tmp_path / "db.sqlite")
        rid = store.create_run(
            agent_id="a1",
            input_="hello",
            workdir="/tmp",
            transcript_path="/tmp/t.jsonl",
        )
        store.save_run_snapshot(
            run_id=rid,
            rendered_prompt={"system": "s", "user": "u"},
            variables={"k": "v"},
            validation_status="warn",
            validation_errors=["field missing"],
        )
        rec = store.get_run(rid)
        assert rec is not None
        assert rec.validation_status == "warn"
        assert rec.validation_errors is not None
        errs = json.loads(rec.validation_errors)
        assert errs == ["field missing"]

    def test_save_run_snapshot_with_composition_snapshot(self, tmp_path: Path) -> None:
        from agentbox.core.data.store import SessionStore

        store = SessionStore(tmp_path / "db.sqlite")
        rid = store.create_run(
            agent_id="a1",
            input_="hello",
            workdir="/tmp",
            transcript_path="/tmp/t.jsonl",
        )
        store.save_run_snapshot(
            run_id=rid,
            rendered_prompt={"system": "s", "user": "u"},
            variables={"k": "v"},
            validation_status="ok",
            validation_errors=[],
            composition_snapshot={"bundle_sha": "abc"},
        )
        rec = store.get_run(rid)
        assert rec is not None
        snap = json.loads(rec.composition_snapshot)
        assert snap["bundle_sha"] == "abc"


class TestPromptCaptureComposed:
    def test_build_fragments_uses_composed_system(self, tmp_path: Path) -> None:
        from agentbox.core.deprecated.definitions import AgentDef, RunnerSpec
        from agentbox.core.prompt.capture import build_fragments

        agent = AgentDef(id="test", runner=RunnerSpec())
        agent.__dict__["_composed_system"] = "Composed system prompt"
        agent.__dict__["_composed_schema"] = {"type": "object"}

        frags = build_fragments(agent, user_input="hello", project_root=tmp_path)
        names = [f.name for f in frags]
        assert "user_input" in names
        assert "agent_system_prompt" in names
        assert "output_schema" in names

        sys_frag = next(f for f in frags if f.name == "agent_system_prompt")
        assert sys_frag.content == "Composed system prompt"
        assert sys_frag.injected_by == "agentbox"

        schema_frag = next(f for f in frags if f.name == "output_schema")
        assert '"type": "object"' in schema_frag.content

    def test_build_fragments_falls_back_to_prompt_path(self, tmp_path: Path) -> None:
        from agentbox.core.deprecated.definitions import AgentDef, RunnerSpec
        from agentbox.core.prompt.capture import build_fragments

        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "system.md").write_text("Legacy prompt")

        agent = AgentDef(
            id="test", prompt_path="prompts/system.md", runner=RunnerSpec()
        )
        frags = build_fragments(agent, user_input="hello", project_root=tmp_path)
        sys_frag = next((f for f in frags if f.name == "agent_system_prompt"), None)
        assert sys_frag is not None
        assert sys_frag.content == "Legacy prompt"
