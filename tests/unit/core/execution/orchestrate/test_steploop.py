"""Unit tests for classify_terminal_error in steploop.py.

Tests cover:
- None / empty input → None
- All 26 known error markers → "failed"
- Case-insensitive matching behaviour
- Unmatched error strings → None
"""

from __future__ import annotations

import pytest

from agentbox.core.data.constants import RunStatus
from agentbox.core.execution.orchestrate.steploop import classify_terminal_error

# Convenience alias so assert statements read clearly.
_FAILED = RunStatus.FAILED.value  # "failed"


# ---------------------------------------------------------------------------
# Parametrised table: every marker in _FAILED_ERROR_MARKERS must map to
# "failed" when embedded in a realistic-looking error message.
# ---------------------------------------------------------------------------

_MARKER_CASES: list[tuple[str, str]] = [
    ("rate_limit_space", "rate limit exceeded after 60 s"),
    ("rate_limit_hyphen", "rate-limit hit on model claude-3"),
    ("rate_limit_underscore", "rate_limit error returned by API"),
    ("ratelimit_concat", "ratelimit: please back off"),
    ("space_429_in_message", "HTTP 429 too many requests"),
    ("429_colon_prefix", "429: quota exceeded"),
    ("quota_generic", "quota exceeded for this billing period"),
    ("overloaded_model", "model overloaded, try again later"),
    ("insufficient_quota", "insufficient_quota on account"),
    ("free_usage_limit_error", "FreeUsageLimitError raised by SDK"),
    ("credits_error", "CreditsError: account balance depleted"),
    ("ai_api_call_error", "AI_APICallError(status=429)"),
    ("auth_error", "AuthError: token rejected"),
    ("unauthorized_error", "UnauthorizedError: 401 forbidden"),
    ("invalid_api_key_underscore", "invalid_api_key provided"),
    ("invalid_api_key_space", "invalid api key supplied in header"),
    ("authentication_error_underscore", "authentication_error from provider"),
    ("authentication_error_space", "authentication error: credentials expired"),
    ("connection_error", "ConnectionError: timed out after 30 s"),
    ("connection_reset_error", "ConnectionResetError peer closed socket"),
    ("connect_timeout", "ConnectTimeout while establishing TCP connection"),
    ("read_timeout", "ReadTimeout waiting for response body"),
    ("econnrefused", "ECONNREFUSED localhost:8080"),
    ("econnreset", "ECONNRESET during stream read"),
    ("output_validation_failed", "output validation failed: field 'result' missing"),
    (
        "exceeded_maximum_output_retries",
        "UnexpectedModelBehavior: Exceeded maximum output retries (3)",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    "error_message",
    [p[1] for p in _MARKER_CASES],
    ids=[p[0] for p in _MARKER_CASES],
)
def test_known_marker_in_error_message_returns_failed(error_message: str) -> None:
    """Every registered error marker maps its containing message to 'failed'."""
    # Arrange – error_message already contains the target substring.

    # Act
    result = classify_terminal_error(error_message)

    # Assert
    assert result == _FAILED


# ---------------------------------------------------------------------------
# Falsy inputs – no marker can match nothing.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_none_input_returns_none() -> None:
    """None error string must short-circuit to None without raising."""
    # Arrange
    err: str | None = None

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result is None


@pytest.mark.unit
def test_empty_string_returns_none() -> None:
    """Empty string is falsy; no marker search should be performed."""
    # Arrange
    err = ""

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# Unmatched strings – genuine unexpected crashes must not be reclassified.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unmatched_generic_crash_returns_none() -> None:
    """An unrecognised error string must not be reclassified as 'failed'."""
    # Arrange
    err = "unexpected python crash in executor thread"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result is None


@pytest.mark.unit
def test_unmatched_assertion_error_returns_none() -> None:
    """AssertionError messages do not contain any known marker."""
    # Arrange
    err = "AssertionError: value was not True"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result is None


@pytest.mark.unit
def test_unmatched_key_error_returns_none() -> None:
    """KeyError messages are not in the known-failure vocabulary."""
    # Arrange
    err = "KeyError: 'output'"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# Case-insensitivity – the function lowercases both sides before matching.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rate_limit_uppercase_returns_failed() -> None:
    """Marker matching is case-insensitive: 'RATE LIMIT' must still match."""
    # Arrange
    err = "RATE LIMIT EXCEEDED"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result == _FAILED


@pytest.mark.unit
def test_connection_error_mixed_case_returns_failed() -> None:
    """Mixed-case variant of a known marker is correctly identified."""
    # Arrange
    err = "connectionerror: failed to reach upstream"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result == _FAILED


@pytest.mark.unit
def test_quota_uppercase_returns_failed() -> None:
    """'QUOTA' in upper-case still triggers the failed classification."""
    # Arrange
    err = "QUOTA EXHAUSTED for organisation"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result == _FAILED


# ---------------------------------------------------------------------------
# Boundary / partial match cases – marker can appear anywhere in string.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_marker_embedded_in_longer_string_returns_failed() -> None:
    """A known marker anywhere inside a long error blob must be detected."""
    # Arrange
    err = (
        "Traceback (most recent call last):\n"
        "  File 'runner.py', line 42\n"
        "pydantic_ai.exceptions.UnexpectedModelBehavior: "
        "Exceeded maximum output retries (5) - schema mismatch on field 'result'"
    )

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result == _FAILED


@pytest.mark.unit
def test_429_without_space_prefix_or_colon_suffix_returns_none() -> None:
    """'429' glued directly to other characters does not match ' 429' or '429:'."""
    # Arrange – no space before 429, no colon after; neither marker fires.
    err = "status429abc"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result is None


@pytest.mark.unit
def test_space_429_marker_fires_when_space_present() -> None:
    """' 429' (with leading space) in the error string triggers the failed classification."""
    # Arrange
    err = "response status 429 from upstream"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert result == _FAILED


@pytest.mark.unit
def test_return_value_is_run_status_failed_string() -> None:
    """Return value is exactly RunStatus.FAILED.value, not a boolean or enum."""
    # Arrange
    err = "rate limit hit"

    # Act
    result = classify_terminal_error(err)

    # Assert
    assert isinstance(result, str)
    assert result == "failed"
    assert result == RunStatus.FAILED.value
