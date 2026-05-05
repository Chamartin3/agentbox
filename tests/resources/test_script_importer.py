"""Tests for ScriptImporter."""

from __future__ import annotations

import pytest
from agentbox.core.resources.importers.base import ImporterContext
from agentbox.core.resources.importers.script import ScriptImporter


def test_python_script_detected_by_extension():
    result = ScriptImporter(filename="run.py", content=b"print('hi')\n").run(
        ImporterContext()
    )
    assert result.suggested_type == "script"
    assert result.metadata is not None
    assert result.metadata["language"] == "python"
    assert result.metadata["line_count"] == 2


def test_shell_script_detected_by_extension():
    result = ScriptImporter(filename="run.sh", content=b"echo hi\n").run(
        ImporterContext()
    )
    assert result.metadata is not None
    assert result.metadata["language"] == "shell"


def test_schema_bindings_passthrough():
    result = ScriptImporter(
        filename="t.py",
        content=b"x = 1\n",
        input_schema_resource_id="res_in",
        output_schema_resource_id="res_out",
    ).run(ImporterContext())
    assert result.metadata is not None
    assert result.metadata["input_schema_resource_id"] == "res_in"
    assert result.metadata["output_schema_resource_id"] == "res_out"


def test_unknown_extension_raises():
    with pytest.raises(ValueError, match="unsupported extension"):
        ScriptImporter(filename="run.rb", content=b"puts 1").run(ImporterContext())


def test_non_utf8_raises():
    with pytest.raises(ValueError, match="not UTF-8"):
        ScriptImporter(filename="t.py", content=b"\xff\xfe\x00").run(ImporterContext())


def test_explicit_language_overrides_extension():
    result = ScriptImporter(
        filename="run.py", content=b"echo hi\n", language="shell"
    ).run(ImporterContext())
    assert result.metadata is not None
    assert result.metadata["language"] == "shell"
