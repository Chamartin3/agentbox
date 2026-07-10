"""resolve_engine bridge — ensure thin wrappers delegate to plugins."""

from __future__ import annotations

import pytest

import agentbox.core.engines.backends.registry as plugins
from agentbox.core.agents import (
    engine_load_failure,
    list_engines,
    resolve_engine_by_name,
)


def test_list_engines_matches_plugins() -> None:
    assert list_engines() == plugins.backends()


def test_resolve_engine_by_name_returns_plugin_class() -> None:
    loaded = list_engines()
    if not loaded:
        pytest.skip("no engine plugins registered")
    name, cls = next(iter(loaded.items()))
    assert resolve_engine_by_name(name) is cls


def test_resolve_engine_by_name_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        resolve_engine_by_name("__definitely_not_a_real_engine__")


def test_engine_load_failure_unknown_returns_none() -> None:
    assert engine_load_failure("__definitely_not_a_real_engine__") is None
