"""Plan 23 — ``resolve_output_config`` reads validators from inline
``config_json["output"].validators`` only (the contract fallback was
retired in Phase 3)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from agentbox.core.agent.config import (
    HttpValidatorConfig,
    ScriptValidatorConfig,
    resolve_output_config,
)


class _Agent:
    """Minimal AgentDef stand-in. ``_config_json`` lives in ``__dict__``
    the same way the DB row mapper attaches it at runtime."""

    def __init__(self, agent_id: str, config_json: dict[str, Any] | None) -> None:
        self.id = agent_id
        self.__dict__["_config_json"] = config_json


class _Store:
    """Stub store. Only the methods ``resolve_output_config`` touches
    are implemented. ``schema_text`` makes the output_schema binding
    optional."""

    def __init__(self, *, schema_text: str | None = None) -> None:
        self._schema_text = schema_text

    # --- schema-side stubs ---
    def list_prompt_bindings(self, _agent_id: str) -> list[dict]:
        if self._schema_text is None:
            return []
        return [
            {"slot": "output_schema", "resource_id": "r1", "pinned_version_id": "v1"}
        ]

    def get_repo_version(self, vid: str) -> dict:
        return {"id": vid}

    def get_active_repo_version(self, _rid: str) -> dict:
        return {"id": "v1"}

    def read_repo_blob(self, _vid: str, _path: str) -> dict:
        return {"content_text": self._schema_text or ""}


def test_inline_validators_resolve() -> None:
    inline_cfg = {
        "output": {
            "validators": [
                {
                    "kind": "http",
                    "endpoint": "http://inline/api",
                    "timeout_seconds": 7,
                    "description": "Inline wins.",
                }
            ]
        }
    }
    agent = _Agent("a1", inline_cfg)
    out = resolve_output_config(_Store(), agent)

    assert len(out.validators) == 1
    v = out.validators[0]
    assert isinstance(v, HttpValidatorConfig)
    assert v.endpoint == "http://inline/api"
    assert v.timeout_seconds == 7
    assert v.description == "Inline wins."


def test_no_config_json_returns_no_validators() -> None:
    agent = _Agent("a1", config_json=None)
    out = resolve_output_config(_Store(), agent)
    assert out.validators == ()
    assert out.json_schema is None


def test_empty_validators_list_returns_no_validators() -> None:
    agent = _Agent("a1", {"output": {"validators": []}})
    out = resolve_output_config(_Store(), agent)
    assert out.validators == ()


def test_inline_config_json_can_be_json_string() -> None:
    """The DB row mapper sometimes hands us the raw JSON column. The
    underlying ``_config_section`` helper already decodes strings — this
    test makes sure the inline-first read path goes through that decode."""
    inline_cfg = {
        "output": {
            "validators": [
                {"kind": "http", "endpoint": "http://x/", "description": "ok."}
            ]
        }
    }
    agent = _Agent("a1", json.dumps(inline_cfg))  # type: ignore[arg-type]
    store = _Store()

    out = resolve_output_config(store, agent)

    assert len(out.validators) == 1
    assert out.validators[0].endpoint == "http://x/"


def test_inline_script_validator_preloads_source() -> None:
    inline_cfg = {
        "output": {
            "validators": [
                {
                    "kind": "script",
                    "resource_id": "script-r",
                    "description": "script desc.",
                }
            ]
        }
    }
    agent = _Agent("a1", inline_cfg)

    class _ScriptStore(_Store):
        def get_active_repo_version(self, rid: str) -> dict:
            assert rid == "script-r"
            return {"id": "ver-1"}

        def read_repo_blob(self, vid: str, _path: str) -> dict:
            assert vid == "ver-1"
            return {"content_text": "def check(out): pass\n"}

    out = resolve_output_config(_ScriptStore(), agent)
    assert len(out.validators) == 1
    v = out.validators[0]
    assert isinstance(v, ScriptValidatorConfig)
    assert v.source_code == "def check(out): pass\n"
    assert v.resource_version_id == "ver-1"
    assert v.description == "script desc."


@pytest.mark.parametrize(
    "broken_entry",
    [
        {"kind": "unknown", "description": "skipped."},
        "not a dict",
        {"kind": "script"},  # missing resource_id
    ],
)
def test_inline_skips_broken_entries(broken_entry: Any) -> None:
    inline_cfg = {
        "output": {
            "validators": [
                broken_entry,
                {"kind": "http", "endpoint": "http://ok/", "description": "ok."},
            ]
        }
    }
    agent = _Agent("a1", inline_cfg)
    out = resolve_output_config(_Store(), agent)
    assert len(out.validators) == 1
    assert out.validators[0].endpoint == "http://ok/"
