"""build_run_env — the per-workspace scrub-and-inject rule.

``creds is None`` inherits the full env (legacy, non-breaking); a dict opts
into least privilege: provider keys scrubbed, only enabled creds injected.
"""

from __future__ import annotations

import pytest

from agentbox.core.engines.backends.credenv import build_run_env


def test_none_inherits_full_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-ambient")
    monkeypatch.setenv("PATH_LIKE", "keepme")
    env = build_run_env(None)
    assert env["OPENROUTER_API_KEY"] == "sk-ambient"  # unconfigured → inherit
    assert env["PATH_LIKE"] == "keepme"


def test_dict_scrubs_provider_keys_and_injects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-ambient")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-openai")
    monkeypatch.setenv("PATH_LIKE", "keepme")
    env = build_run_env({"OPENAI_API_KEY": "sk-granted"})
    # ambient provider keys are scrubbed...
    assert "OPENROUTER_API_KEY" not in env
    # ...and only the enabled credential is present (with the granted value).
    assert env["OPENAI_API_KEY"] == "sk-granted"
    # non-credential env is preserved.
    assert env["PATH_LIKE"] == "keepme"


def test_empty_dict_scrubs_all_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-ambient")
    env = build_run_env({})
    assert "OPENROUTER_API_KEY" not in env
