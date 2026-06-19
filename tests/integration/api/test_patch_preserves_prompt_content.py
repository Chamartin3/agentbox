"""Regression tests for the prompt_content-loss bug.

Bug: ``PATCH /api/agents/{id}`` and ``PUT /api/agents/{id}/validation``
created a new ``agent_versions`` row without carrying forward
``prompt_content`` from the previously-active version. Result: the
new version had ``prompt_content=NULL`` and the runtime crashed with
"agent X has no prompt source".

These tests reproduce the bug by creating an agent with prompt_content
set, applying a config-only mutation (webhook_url / validators), and
asserting the new active version preserves the prompt body.
"""

from __future__ import annotations

import contextlib
import warnings

import pytest
from agentbox.api.app import create_app
from fastapi.testclient import TestClient

# resolve_agent serializes session_mode back as a str default, which trips
# pydantic's UnexpectedValue warning -> pytest "filterwarnings = error".
# That warning is unrelated to the prompt_content regression we're testing,
# so silence it locally.
pytestmark = pytest.mark.filterwarnings(
    "ignore::UserWarning",
)
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=".*PydanticSerializationUnexpectedValue.*",
)


class _ManagedTestClient(TestClient):
    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.__exit__(None, None, None)


_PROMPT_BODY = "You are a test agent. Emit a single JSON object."


def _app(_tmp_path):
    import agentbox.api.deps as deps

    for fn in (
        deps.get_settings,
        deps.get_store,
        deps.get_executor,
        deps.get_mcp_registry,
    ):
        fn.cache_clear()
    client = _ManagedTestClient(create_app())
    client.__enter__()
    store = deps.get_store()
    return client, store


def _create_db_only_agent(store) -> dict:
    """Create a DB-only agent with prompt_content set (no disk file)."""
    config_json = {
        "id": "patch-prompt-agent",
        "description": "regression test agent",
        "runner": {"kind": "claude_code", "model": "haiku"},
    }
    v1 = store.create_agent(
        agent_id="patch-prompt-agent",
        config_json=config_json,
        author="test",
        changelog="initial",
        prompt_content=_PROMPT_BODY,
        source="ui",
    )
    # Publish + activate v1 so PATCH/validation see it as the active version.
    store.publish_version("patch-prompt-agent", v1["version"], reason="seed")
    store.activate_version("patch-prompt-agent", v1["id"])
    return v1


class TestPatchPreservesPromptContent:
    def test_patch_webhook_url_keeps_prompt_content(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        _create_db_only_agent(store)

        resp = client.patch(
            "/api/agents/patch-prompt-agent",
            json={"webhook_url": "http://example.com/hook"},
        )
        assert resp.status_code == 200, resp.text

        # The latest version is what the runtime resolves to. PATCH must
        # carry forward prompt_content into the new row, whether or not
        # it also bumps the active pointer.
        latest = store.latest_version("patch-prompt-agent")
        assert latest is not None
        assert latest.get("prompt_content") == _PROMPT_BODY, (
            f"PATCH dropped prompt_content; latest row has "
            f"prompt_content={latest.get('prompt_content')!r}"
        )

    def test_patch_activates_new_version(self, isolated_data_dir) -> None:
        """PATCH must activate the new row.

        If it doesn't, a follow-up call that reads the active row (e.g.
        PUT /validation rebuilding config_json from active) operates on
        stale data and overwrites whatever the PATCH just changed.
        That's how composition got clobbered in stage.generate_generic.
        """
        client, store = _app(isolated_data_dir)
        _create_db_only_agent(store)

        resp = client.patch(
            "/api/agents/patch-prompt-agent",
            json={"webhook_url": "http://example.com/hook"},
        )
        assert resp.status_code == 200, resp.text

        latest = store.latest_version("patch-prompt-agent")
        active = store.get_active_version("patch-prompt-agent")
        assert latest is not None and active is not None
        assert active["id"] == latest["id"], (
            f"PATCH did not activate the new version: "
            f"active id={active['id']} latest id={latest['id']}"
        )


class TestPatchPreservesValidators:
    """``PATCH /api/agents/{id}`` rebuilds ``config_json`` from ``AgentDef``,
    which has no field for inline validators. Without an explicit merge,
    PATCH silently clobbers the ``output.validators`` written by
    ``PUT /validation`` — exactly the bug that caused stage.draft_fixer
    to skip Gate-2 (length floor) for every run after a webhook_url patch.
    """

    def test_patch_webhook_url_preserves_validators(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        _create_db_only_agent(store)

        validators_payload = [
            {
                "kind": "http",
                "endpoint": "http://example.com/validate",
                "timeout_seconds": 5,
                "description": "rendered length must exceed 2300 chars",
            }
        ]
        seed = client.put(
            "/api/agents/patch-prompt-agent/validation",
            json={"output": {"validators": validators_payload}, "reason": "seed"},
        )
        assert seed.status_code == 200, seed.text

        patch = client.patch(
            "/api/agents/patch-prompt-agent",
            json={"webhook_url": "http://example.com/hook"},
        )
        assert patch.status_code == 200, patch.text

        after = client.get("/api/agents/patch-prompt-agent/validation").json()
        stored = (after.get("output") or {}).get("validators") or []
        assert len(stored) == 1, (
            f"PATCH dropped inline validators; "
            f"got {len(stored)} on the new active version"
        )
        assert stored[0]["endpoint"] == validators_payload[0]["endpoint"]
        assert stored[0]["description"] == validators_payload[0]["description"]


class TestValidationPreservesPromptContent:
    def test_put_validation_keeps_prompt_content(self, isolated_data_dir) -> None:
        client, store = _app(isolated_data_dir)
        _create_db_only_agent(store)

        resp = client.put(
            "/api/agents/patch-prompt-agent/validation",
            json={
                "output": {
                    "validators": [
                        {
                            "kind": "http",
                            "endpoint": "http://example.com/validate",
                            "timeout_seconds": 5,
                            "description": "test validator",
                        }
                    ]
                },
                "reason": "test",
            },
        )
        assert resp.status_code == 200, resp.text

        active = store.get_active_version("patch-prompt-agent")
        assert active is not None
        assert active.get("prompt_content") == _PROMPT_BODY, (
            "PUT /validation dropped prompt_content from the active version"
        )
