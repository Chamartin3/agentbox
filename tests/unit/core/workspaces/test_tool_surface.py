"""Unified tool surface merge — adapter-declared ⊕ built-in complement.

Precedence: adapter-declared native tools override same-named built-ins; the
built-in vocabulary fills the gaps. (MCP/host-env/resource slices need a DB and
are covered by the catalog integration tests.)
"""

from __future__ import annotations

from agentbox.core.tools.canonical import CanonicalTool
from agentbox.core.tools.catalog import enumerate_callables
from agentbox.core.workspaces.tooling.catalog import (
    _builtin_complement_callables,
    _declared_tool_callables,
)


def test_adapter_declared_overrides_builtin_complement() -> None:
    declared = _declared_tool_callables([CanonicalTool.FS_READ])
    complement = _builtin_complement_callables()

    # declared slice first → adapter wins on fs.read
    merged = enumerate_callables([declared, complement])

    reads = [i for i in merged if i.name == "fs.read"]
    assert len(reads) == 1
    assert reads[0].kind == "builtin"
    # the complement still contributes tools the adapter didn't declare
    assert any(i.name == "git.status" for i in merged)


def test_no_declared_tools_is_just_the_complement() -> None:
    assert _declared_tool_callables(None) == []
    assert _declared_tool_callables([]) == []
    # complement covers the canonical vocabulary
    names = {i.name for i in _builtin_complement_callables()}
    assert "fs.read" in names and "shell.exec" in names
