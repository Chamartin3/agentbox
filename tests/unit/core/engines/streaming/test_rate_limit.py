"""Unit tests for agentbox.core.engines.streaming.rate_limit.

Covers detect_in_opencode_event, detect_in_text_line, _walk_for_api_error,
and _try_parse_trailing_json.  All functions under test are pure — no mocks,
no fixtures, no I/O.
"""

from __future__ import annotations

import json

import pytest

from agentbox.core.engines.streaming.rate_limit import (
    _try_parse_trailing_json,
    _walk_for_api_error,
    detect_in_opencode_event,
    detect_in_text_line,
)


# ---------------------------------------------------------------------------
# TestDetectInOpencodeEvent
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectInOpencodeEvent:
    """Tests for detect_in_opencode_event."""

    # -- Fatal status-code events via top-level type==error envelope --

    def test_401_status_in_error_envelope_returns_non_none(self) -> None:
        """Verify that a 401 status code inside an error envelope is treated as fatal."""
        # Arrange
        evt = {"type": "error", "error": {"name": "AuthError", "statusCode": 401}}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None
        # The result must mention the name or status so the caller can log it
        assert "AuthError" in result or "401" in result

    def test_402_status_with_message_surfaces_message(self) -> None:
        """Verify a 402 error envelope returns the provider message."""
        # Arrange
        evt = {"type": "error", "error": {"statusCode": 402, "message": "credits"}}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None
        assert "credits" in result

    def test_403_status_in_error_envelope_returns_non_none(self) -> None:
        """Verify a 403 UnauthorizedError inside the error envelope is fatal."""
        # Arrange
        evt = {
            "type": "error",
            "error": {"name": "UnauthorizedError", "statusCode": 403},
        }

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None

    def test_429_status_in_error_envelope_returns_non_none(self) -> None:
        """Verify a 429 AI_APICallError inside the error envelope is fatal."""
        # Arrange
        evt = {
            "type": "error",
            "error": {"name": "AI_APICallError", "statusCode": 429},
        }

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None

    # -- Fatal error names walking the full event (no outer type==error) --

    @pytest.mark.parametrize(
        "err_name",
        [
            "AI_APICallError",
            "FreeUsageLimitError",
            "AuthError",
            "CreditsError",
            "APIError",
            "UnauthorizedError",
        ],
        ids=[
            "ai_apicallerror",
            "free_usage_limit",
            "auth_error",
            "credits_error",
            "api_error",
            "unauthorized_error",
        ],
    )
    def test_fatal_error_name_without_type_field_returns_non_none(
        self, err_name: str
    ) -> None:
        """Verify events carrying a known fatal error name are detected even without type==error."""
        # Arrange
        evt = {"name": err_name}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None

    # -- Top-level type==error with non-dict inner payload --

    def test_type_error_with_string_inner_returns_error_event_message(self) -> None:
        """Verify a string error payload inside type==error still surfaces as fatal."""
        # Arrange
        evt = {"type": "error", "error": "string error"}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None
        assert "error event" in result

    def test_type_error_with_none_inner_uses_fallback_message(self) -> None:
        """Verify type==error with error=None returns a fallback message."""
        # Arrange
        evt = {"type": "error", "error": None}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None
        assert "no error payload" in result

    # -- Nested data dict extraction (newer opencode shape) --

    def test_nested_data_statuscode_surfaces_message(self) -> None:
        """Verify statusCode inside a nested data dict is picked up and message returned."""
        # Arrange
        evt = {
            "name": "AI_APICallError",
            "data": {"statusCode": 429, "message": "rate limited"},
        }

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None
        assert "rate limited" in result

    def test_nested_responsebody_in_data_extracts_message(self) -> None:
        """Verify responseBody nested inside data is unwrapped to produce a message."""
        # Arrange
        response_body = json.dumps(
            {"type": "error", "error": {"message": "quota exceeded"}}
        )
        evt = {
            "name": "AI_APICallError",
            "data": {"responseBody": response_body},
        }

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is not None

    # -- Non-fatal / safe events --

    def test_text_event_returns_none(self) -> None:
        """Verify a normal text event does not trigger the rate-limit detector."""
        # Arrange
        evt = {"type": "text", "content": "hello"}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is None

    def test_assistant_completion_event_returns_none(self) -> None:
        """Verify a well-formed assistant message event returns None."""
        # Arrange
        evt = {"type": "assistant", "message": {"content": []}}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is None

    def test_200_status_with_unknown_error_name_returns_none(self) -> None:
        """Verify that a non-fatal HTTP status with an unknown name is not flagged."""
        # Arrange
        evt = {"statusCode": 200, "name": "SomeOtherError"}

        # Act
        result = detect_in_opencode_event(evt)

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# TestDetectInTextLine
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectInTextLine:
    """Tests for detect_in_text_line."""

    def test_empty_line_returns_none(self) -> None:
        """Verify an empty string returns None."""
        # Arrange / Act / Assert
        assert detect_in_text_line("") is None

    def test_whitespace_only_line_returns_none(self) -> None:
        """Verify a whitespace-only line returns None."""
        # Arrange / Act / Assert
        assert detect_in_text_line("   \t\n") is None

    def test_unrelated_line_returns_none(self) -> None:
        """Verify a line with no rate-limit indicators returns None."""
        # Arrange / Act / Assert
        assert detect_in_text_line("INFO: processing completed successfully") is None

    @pytest.mark.parametrize(
        "line",
        [
            "HTTP 429 rate limit exceeded",
            "rate-limit error encountered",
            "rate_limit hit on the provider",
            "quota exceeded for model gpt-4",
            "model is overloaded, please retry",
            "insufficient_quota for this key",
            "FreeUsageLimitError thrown by provider",
            "invalid_api_key provided in header",
            "authentication_error: bad key supplied",
            "AI_RetryError: maxRetriesExceeded",
            "CreditsError: account has no credits",
        ],
        ids=[
            "429_literal",
            "rate_limit_hyphen",
            "rate_limit_underscore",
            "quota",
            "overloaded",
            "insufficient_quota",
            "free_usage_limit",
            "invalid_api_key",
            "authentication_error",
            "ai_retry_error",
            "credits_error",
        ],
    )
    def test_known_pattern_line_returns_non_none(self, line: str) -> None:
        """Verify each known rate-limit / auth failure pattern triggers detection."""
        # Arrange / Act
        result = detect_in_text_line(line)

        # Assert
        assert result is not None

    def test_result_truncated_to_300_chars_for_long_plain_line(self) -> None:
        """Verify the returned string is never longer than 300 characters."""
        # Arrange — line is long but contains '429' to trigger the pattern
        long_line = "HTTP 429 rate limited: " + "x" * 500

        # Act
        result = detect_in_text_line(long_line)

        # Assert
        assert result is not None
        assert len(result) <= 300

    def test_structured_opencode_log_line_returns_compact_summary(self) -> None:
        """Verify a structured opencode log line is pretty-printed, not returned raw."""
        # Arrange
        error_json = json.dumps(
            {
                "error": {
                    "name": "AI_APICallError",
                    "data": {"statusCode": 429, "message": "rate limited"},
                }
            }
        )
        line = (
            f"ERROR 2026-01-01T00:00:00 service=llm providerID=anthropic "
            f"modelID=claude-3-5 error={error_json}"
        )

        # Act
        result = detect_in_text_line(line)

        # Assert
        assert result is not None
        # The pretty-printer must produce a compact summary — not the raw ERROR line
        assert not result.startswith("ERROR")
        assert "429" in result or "AI_APICallError" in result

    def test_plain_rate_limit_line_without_json_falls_back_to_raw(self) -> None:
        """Verify a line with no structured JSON falls back to the raw truncated text."""
        # Arrange
        line = "rate_limit error — no JSON payload here"

        # Act
        result = detect_in_text_line(line)

        # Assert
        assert result is not None
        # Falls back to raw text; must contain original signal
        assert "rate" in result.lower()


# ---------------------------------------------------------------------------
# TestWalkForApiError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWalkForApiError:
    """Tests for _walk_for_api_error."""

    def test_finds_fatal_status_at_root(self) -> None:
        """Verify a 429 statusCode at the root level is detected immediately."""
        # Arrange
        node = {"statusCode": 429}

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is not None
        status, name, _message = result
        assert status == 429
        assert name is None

    def test_finds_fatal_name_at_root(self) -> None:
        """Verify a fatal error name at the root level is detected."""
        # Arrange
        node = {"name": "AuthError"}

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is not None
        status, name, _message = result
        assert name == "AuthError"
        assert status is None

    def test_finds_nested_status_in_deep_dict(self) -> None:
        """Verify recursive dict traversal finds a fatal statusCode several levels down."""
        # Arrange
        node = {"outer": {"inner": {"statusCode": 401}}}

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is not None
        status, _name, _message = result
        assert status == 401

    def test_finds_fatal_status_inside_list(self) -> None:
        """Verify list items are walked when searching for fatal errors."""
        # Arrange
        node = [{"statusCode": 403}]

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is not None
        status, _name, _message = result
        assert status == 403

    def test_depth_cap_prevents_detection_beyond_seven_levels(self) -> None:
        """Verify recursion is capped so a fatal node 8 levels deep is not surfaced."""
        # Arrange — wrap a 429 node 8 levels deep; depth cap is > 6, so depth 7 returns None
        innermost: dict = {"statusCode": 429}
        node: dict = innermost
        for _ in range(8):
            node = {"child": node}

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is None

    def test_200_status_not_in_fatal_set_returns_none(self) -> None:
        """Verify a 200 statusCode does not trigger a fatal classification."""
        # Arrange
        node = {"statusCode": 200}

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is None

    def test_none_input_returns_none(self) -> None:
        """Verify None input is handled gracefully."""
        # Arrange / Act
        result = _walk_for_api_error(None)

        # Assert
        assert result is None

    def test_extracts_message_from_response_body_string(self) -> None:
        """Verify a JSON-encoded responseBody is unwrapped to produce the message."""
        # Arrange
        response_body = json.dumps({"error": {"message": "credit limit reached"}})
        node = {
            "name": "AI_APICallError",
            "statusCode": 429,
            "responseBody": response_body,
        }

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is not None
        _status, _name, message = result
        assert message is not None
        assert "credit limit" in message

    def test_merges_statuscode_from_nested_data_dict(self) -> None:
        """Verify statusCode nested inside a 'data' key is merged with the parent name."""
        # Arrange
        node = {
            "name": "AI_APICallError",
            "data": {"statusCode": 429, "message": "too many requests"},
        }

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is not None
        status, name, message = result
        assert status == 429
        assert name == "AI_APICallError"
        assert message == "too many requests"

    def test_unknown_name_and_non_fatal_status_returns_none(self) -> None:
        """Verify an event with no known name and a non-fatal status returns None."""
        # Arrange
        node = {"name": "UnknownError", "statusCode": 500}

        # Act
        result = _walk_for_api_error(node)

        # Assert
        assert result is None

    def test_empty_dict_returns_none(self) -> None:
        """Verify an empty dict does not match any fatal condition."""
        # Arrange / Act
        result = _walk_for_api_error({})

        # Assert
        assert result is None

    def test_empty_list_returns_none(self) -> None:
        """Verify an empty list does not match any fatal condition."""
        # Arrange / Act
        result = _walk_for_api_error([])

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# TestTryParseTrailingJson
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTryParseTrailingJson:
    """Tests for _try_parse_trailing_json."""

    def test_clean_json_object_is_parsed(self) -> None:
        """Verify a clean JSON object string is parsed into a dict."""
        # Arrange
        s = '{"a": 1}'

        # Act
        result = _try_parse_trailing_json(s)

        # Assert
        assert result == {"a": 1}

    def test_json_object_with_trailing_garbage_is_parsed(self) -> None:
        """Verify trailing non-JSON text after a balanced object is ignored."""
        # Arrange
        s = '{"a": 1}rest of the log line goes here'

        # Act
        result = _try_parse_trailing_json(s)

        # Assert
        assert result == {"a": 1}

    def test_non_object_json_returns_none(self) -> None:
        """Verify a JSON string literal (not an object) returns None."""
        # Arrange
        s = '"just a string"'

        # Act
        result = _try_parse_trailing_json(s)

        # Assert
        assert result is None

    def test_non_json_input_returns_none(self) -> None:
        """Verify plain text with no JSON returns None."""
        # Arrange
        s = "not json at all"

        # Act
        result = _try_parse_trailing_json(s)

        # Assert
        assert result is None

    def test_truncated_json_with_no_closing_brace_returns_none(self) -> None:
        """Verify a truncated JSON object with no closing brace returns None."""
        # Arrange
        s = '{"a": 1, "b":'

        # Act
        result = _try_parse_trailing_json(s)

        # Assert
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        """Verify an empty string returns None."""
        # Arrange / Act
        result = _try_parse_trailing_json("")

        # Assert
        assert result is None

    def test_nested_json_object_is_fully_parsed(self) -> None:
        """Verify deeply nested JSON objects are parsed correctly."""
        # Arrange
        payload = {"outer": {"inner": {"statusCode": 429, "message": "limited"}}}
        s = json.dumps(payload) + " trailing text"

        # Act
        result = _try_parse_trailing_json(s)

        # Assert
        assert result == payload

    def test_json_with_escaped_braces_in_strings_is_parsed(self) -> None:
        """Verify JSON strings containing brace characters do not confuse the parser."""
        # Arrange
        s = '{"message": "error in {block} context"}'

        # Act
        result = _try_parse_trailing_json(s)

        # Assert
        assert result == {"message": "error in {block} context"}
