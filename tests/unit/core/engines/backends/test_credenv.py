"""build_run_env — including the ``extra`` workspace-env-var argument."""
from __future__ import annotations

from agentbox.core.engines.backends.credenv import build_run_env


def test_extra_merged_after_os_environ() -> None:
    """Workspace extra vars appear in the returned env."""
    env = build_run_env(creds=None, extra={"FOO": "bar"})
    assert env["FOO"] == "bar"


def test_extra_does_not_override_provider_keys() -> None:
    """A workspace var named like a provider key is not treated as a credential."""
    env = build_run_env(
        creds={"OPENAI_API_KEY": "cred-value"},
        extra={"OPENAI_API_KEY": "ws-value"},
    )
    assert env["OPENAI_API_KEY"] == "cred-value"


def test_extra_visible_when_no_cred_conflict() -> None:
    """Workspace extra vars that don't collide with creds are present."""
    env = build_run_env(
        creds={"OPENAI_API_KEY": "cred-value"},
        extra={"MY_CUSTOM_VAR": "hello"},
    )
    assert env["MY_CUSTOM_VAR"] == "hello"
    assert env["OPENAI_API_KEY"] == "cred-value"


def test_extra_alone_without_creds() -> None:
    """extra without creds still includes os.environ minus provider keys."""
    env = build_run_env(creds=None, extra={"X": "1"})
    assert env["X"] == "1"
    # Provider keys are scrubbed when extra is provided (the workspace has
    # opted into custom env, which triggers the least-privilege scrub path).
    from agentbox.core.data.constants import PROVIDER_KEY_ENV_VARS

    for key in PROVIDER_KEY_ENV_VARS:
        assert key not in env
    # Non-provider os.environ vars are still inherited.
    assert "PATH" in env


def test_creds_alone_without_extra() -> None:
    """Backward-compat: creds without extra still scrubs provider keys."""
    env = build_run_env(creds={"OPENAI_API_KEY": "k"})
    assert env["OPENAI_API_KEY"] == "k"
    # Other provider keys should be scrubbed.
    from agentbox.core.data.constants import PROVIDER_KEY_ENV_VARS

    for key in PROVIDER_KEY_ENV_VARS:
        if key != "OPENAI_API_KEY":
            assert key not in env
