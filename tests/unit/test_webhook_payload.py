"""Webhook payload contract tests.

Verify that ``webhook_payload`` and ``_parsed_output`` maintain a
stable, unambiguous wire contract regardless of backend.
"""

from __future__ import annotations

import json

from agentbox.api.webhooks import (
    _parsed_output,
    _parsed_output_structured,
    webhook_payload,
)
from agentbox.core.data import RunRecord


def _make_run(output: str, validation_status: str = "ok") -> RunRecord:
    return RunRecord(
        id="run-1",
        agent_id="test-agent",
        session_id=None,
        status="ok",
        input='{"url": "https://example.com"}',
        output=output,
        error=None,
        workdir=None,
        transcript_path=None,
        created_at="2024-01-01T00:00:00",
        finished_at="2024-01-01T00:01:00",
        validation_status=validation_status,
        validation_errors=None,
        schema_validated_via="both",
    )


def test_output_is_always_string():
    """``output`` field must always be a string — never a dict or list."""
    payload = webhook_payload(
        _make_run('{"key": "value"}'),
        usage=None,
        duration_ms=None,
    )
    assert isinstance(payload["output"], str), (
        f"output must be str, got {type(payload['output']).__name__}"
    )
    assert payload["output"] == '{"key": "value"}'


def test_output_structured_is_dict_when_valid():
    """``output_structured`` is a dict when validation passes and output is JSON."""
    payload = webhook_payload(
        _make_run('{"key": "value"}'),
        usage=None,
        duration_ms=None,
    )
    assert payload["output_structured"] == {"key": "value"}


def test_output_structured_is_none_when_not_validated():
    """``output_structured`` is None when validation didn't pass."""
    payload = webhook_payload(
        _make_run('{"key": "value"}', validation_status="fail"),
        usage=None,
        duration_ms=None,
    )
    assert payload["output_structured"] is None


def test_output_structured_is_none_when_not_json():
    """``output_structured`` is None when output isn't parseable JSON."""
    payload = webhook_payload(
        _make_run("plain text output"),
        usage=None,
        duration_ms=None,
    )
    assert payload["output_structured"] is None


def test_output_never_dict_or_list():
    """Even structured JSON output must be serialized as a string in ``output``."""
    payload = webhook_payload(
        _make_run(json.dumps({"nested": [1, 2, 3]})),
        usage=None,
        duration_ms=None,
    )
    assert isinstance(payload["output"], str)
    # Round-trip through JSON serialization should keep output as string
    serialized = json.loads(json.dumps(payload))
    assert isinstance(serialized["output"], str)


def test_output_empty_string_when_none():
    """Empty or None run.output should be handled gracefully."""
    payload = webhook_payload(
        _make_run(""),
        usage=None,
        duration_ms=None,
    )
    assert payload["output"] == ""
    assert payload["output_structured"] is None


def test_parsed_output_always_string():
    """``_parsed_output`` returns raw string unconditionally."""
    assert _parsed_output(_make_run('{"a": 1}')) == '{"a": 1}'
    assert _parsed_output(_make_run("hello")) == "hello"
    assert _parsed_output(_make_run("")) == ""


def test_parsed_output_structured_none_when_invalid():
    """``_parsed_output_structured`` returns None on non-validated runs."""
    assert (
        _parsed_output_structured(_make_run('{"a": 1}', validation_status="fail"))
        is None
    )
    assert _parsed_output_structured(_make_run("not json")) is None
    assert _parsed_output_structured(_make_run("")) is None
