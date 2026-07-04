"""Tests for domain enums — no magic strings."""

from __future__ import annotations

from agentbox.core.data.constants import (
    BundleFile,
    EventType,
    ResourceType,
    RunStatus,
    SessionMode,
)


def test_run_status_terminal_values() -> None:
    assert RunStatus.OK == "ok"
    assert RunStatus.ERROR == "error"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.TIMEOUT == "timeout"
    assert RunStatus.INCOMPLETE == "incomplete"


def test_event_type_discriminators() -> None:
    assert EventType.TEXT == "text"
    assert EventType.USAGE == "usage"
    assert EventType.DONE == "done"
    assert EventType.VALIDATION == "validation"
    assert EventType.RETRY == "retry"


def test_resource_type_values() -> None:
    assert ResourceType.DOCUMENT == "document"
    assert ResourceType.FOLDER == "folder"
    assert ResourceType.SKILL == "skill"
    assert ResourceType.SCHEMA == "schema"
    assert ResourceType.SCRIPT == "script"


def test_bundle_file_paths() -> None:
    assert BundleFile.SYSTEM_PROMPT == "prompts/system.md"
    assert BundleFile.OUTPUT_SCHEMA == "output_schema.json"


def test_session_mode_values() -> None:
    assert SessionMode.HEADLESS == "headless"
    assert SessionMode.PERSISTENT == "persistent"
