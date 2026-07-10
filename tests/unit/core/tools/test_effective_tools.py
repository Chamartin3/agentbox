"""The single tool-authorization formula (plan 122).

    base      = available                if allowed is empty
              = allowed ∩ available       otherwise
    effective = base − forbidden
"""

from __future__ import annotations

from agentbox.core.tools.translation import effective_tool_set

AVAILABLE = {"fs.read", "fs.write", "shell.exec", "web.fetch"}


def test_no_lists_grants_all() -> None:
    assert effective_tool_set(allowed=set(), forbidden=set(), available=AVAILABLE) == AVAILABLE


def test_allow_only_intersects_available() -> None:
    # allow-list is today's behavior — unchanged. Only listed tools survive,
    # and a listed tool not in `available` is dropped (intersection).
    got = effective_tool_set(
        allowed={"fs.read", "shell.exec", "not.available"},
        forbidden=set(),
        available=AVAILABLE,
    )
    assert got == {"fs.read", "shell.exec"}


def test_forbidden_only_subtracts_from_all() -> None:
    got = effective_tool_set(allowed=set(), forbidden={"shell.exec"}, available=AVAILABLE)
    assert got == {"fs.read", "fs.write", "web.fetch"}


def test_allow_and_forbidden_combine() -> None:
    got = effective_tool_set(
        allowed={"fs.read", "fs.write", "shell.exec"},
        forbidden={"shell.exec"},
        available=AVAILABLE,
    )
    assert got == {"fs.read", "fs.write"}


def test_forbidden_not_in_available_is_noop() -> None:
    got = effective_tool_set(
        allowed=set(), forbidden={"does.not.exist"}, available=AVAILABLE
    )
    assert got == AVAILABLE


def test_forbidden_wins_over_allow() -> None:
    # A tool both allowed and forbidden is denied — deny is the last term.
    got = effective_tool_set(
        allowed={"fs.read"}, forbidden={"fs.read"}, available=AVAILABLE
    )
    assert got == set()
