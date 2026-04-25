"""Tests for executor composition integration, especially validation modes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from agentbox.api.events import DoneEvent, RunEvent, TextEvent
from agentbox.config import Settings
from agentbox.core.backends.base import RenderedConfig
from agentbox.core.data import SessionStore
from agentbox.core.definitions import DefinitionLoader
from agentbox.core.executor import RunExecutor


class _EchoAdapter:
    """Yields the input text back as output, then DoneEvent(ok=True).

    The composer auto-appends an output-schema instruction block when the
    bundle declares one — a real agent would respond with just the JSON
    object, so we strip everything from the schema block onward to keep
    the echoed payload parseable.
    """

    name = "echo_composition"

    def render(self, agent, workdir, mcp_tools=None, creds=None):  # type: ignore[no-untyped-def]
        return RenderedConfig(argv=["true"], cwd=Path("."))

    async def run(
        self, rendered: RenderedConfig, input: str, run_id: str
    ) -> AsyncIterator[RunEvent]:
        text = input.split("\n\n# Required Output", 1)[0]
        yield TextEvent(run_id=run_id, text=text)
        yield DoneEvent(run_id=run_id, ok=True)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        manifest_path=tmp_path / "manifest.toml",
        data_dir=tmp_path,
        db_path=tmp_path / "db.sqlite",
        port=0,
        host="127.0.0.1",
        agents_dir=None,
        prompts_dir=None,
        skills_dir=None,
        outputs_dir=None,
        completion_webhook_url=None,
        creds_dir=Path("/agentbox/creds"),
    )


def _register(name: str, cls: type) -> None:
    import agentbox.core.plugins as plugins

    plugins.backends()
    plugins._BACKEND_CLASSES[name] = cls  # type: ignore[index]


def _executor(tmp_path: Path) -> RunExecutor:
    settings = _settings(tmp_path)
    store = SessionStore(settings.db_path)
    return RunExecutor(store, settings, DefinitionLoader(settings.project_root))


def _write_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "agents" / "test.agent"
    bundle.mkdir(parents=True)
    (bundle / "agent.toml").write_text(
        'id = "test.agent"\n'
        "[composition]\n"
        'system_prompt = "prompts/system.md"\n'
        'output_schema = "output_schema.json"\n',
        encoding="utf-8",
    )
    prompts = bundle / "prompts"
    prompts.mkdir()
    (prompts / "system.md").write_text("You are {role}.", encoding="utf-8")
    (bundle / "output_schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"result": {"type": "string"}},
                "required": ["result"],
            }
        ),
        encoding="utf-8",
    )
    return bundle


class TestValidationModes:
    def test_strict_mode_fails_on_invalid_output(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("echo_composition", _EchoAdapter)
        executor = _executor(tmp_path)

        _write_bundle(tmp_path)
        loader = DefinitionLoader(tmp_path)
        agent = loader.get("test.agent")
        assert agent is not None
        # Ensure strict mode
        agent = agent.model_copy(
            update={
                "composition": agent.composition.model_copy(
                    update={"output_validation": "strict"}
                )
            }
        )

        async def go() -> str:
            # The echo adapter outputs the input text. If we send invalid JSON,
            # validation should fail after retries.
            rid = await executor.execute(
                agent,
                input_="not json",
                variables={"role": "test", "user_message": "not json"},
                backend="echo_composition",
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())
        rec = executor.store.get_run(rid)
        assert rec is not None
        assert rec.status == "error"
        assert rec.validation_status == "fail"

    def test_warn_mode_ok_with_invalid_output(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("echo_composition", _EchoAdapter)
        executor = _executor(tmp_path)

        _write_bundle(tmp_path)
        loader = DefinitionLoader(tmp_path)
        agent = loader.get("test.agent")
        assert agent is not None
        agent = agent.model_copy(
            update={
                "composition": agent.composition.model_copy(
                    update={"output_validation": "warn"}
                )
            }
        )

        async def go() -> str:
            rid = await executor.execute(
                agent,
                input_='{"missing": "result"}',
                variables={"role": "test", "user_message": '{"missing": "result"}'},
                backend="echo_composition",
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())
        rec = executor.store.get_run(rid)
        assert rec is not None
        assert rec.status == "ok"
        assert rec.validation_status == "warn"
        assert rec.validation_errors is not None

    def test_off_mode_skips_validation(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("echo_composition", _EchoAdapter)
        executor = _executor(tmp_path)

        _write_bundle(tmp_path)
        loader = DefinitionLoader(tmp_path)
        agent = loader.get("test.agent")
        assert agent is not None
        agent = agent.model_copy(
            update={
                "composition": agent.composition.model_copy(
                    update={"output_validation": "off"}
                )
            }
        )

        async def go() -> str:
            rid = await executor.execute(
                agent,
                input_="anything",
                variables={"role": "test", "user_message": "anything"},
                backend="echo_composition",
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())
        rec = executor.store.get_run(rid)
        assert rec is not None
        assert rec.status == "ok"
        assert rec.validation_status is None

    def test_strict_mode_retries_then_fails(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("echo_composition", _EchoAdapter)
        executor = _executor(tmp_path)

        _write_bundle(tmp_path)
        loader = DefinitionLoader(tmp_path)
        agent = loader.get("test.agent")
        assert agent is not None
        # Allow one retry
        agent = agent.model_copy(
            update={
                "composition": agent.composition.model_copy(
                    update={"output_validation": "strict"}
                ),
                "runner": agent.runner.model_copy(update={"max_validation_retries": 1}),
            }
        )

        async def go() -> str:
            rid = await executor.execute(
                agent,
                input_="bad",
                variables={"role": "test", "user_message": "bad"},
                backend="echo_composition",
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())
        rec = executor.store.get_run(rid)
        assert rec is not None
        assert rec.status == "error"
        # Prompt should have been mutated with retry text on second attempt
        assert rec.input is not None

    def test_strict_mode_passes_on_valid_output(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("AGENTBOX_DATA_DIR", str(tmp_path))
        _register("echo_composition", _EchoAdapter)
        executor = _executor(tmp_path)

        _write_bundle(tmp_path)
        loader = DefinitionLoader(tmp_path)
        agent = loader.get("test.agent")
        assert agent is not None
        agent = agent.model_copy(
            update={
                "composition": agent.composition.model_copy(
                    update={"output_validation": "strict"}
                )
            }
        )

        async def go() -> str:
            rid = await executor.execute(
                agent,
                input_='{"result": "hello"}',
                variables={"role": "test", "user_message": '{"result": "hello"}'},
                backend="echo_composition",
            )
            b = executor.broadcaster(rid)
            assert b is not None
            q = b.subscribe()
            while await q.get() is not None:
                pass
            return rid

        rid = asyncio.run(go())
        rec = executor.store.get_run(rid)
        assert rec is not None
        assert rec.status == "ok"
        assert rec.validation_status == "ok"
