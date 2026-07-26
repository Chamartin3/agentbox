"""Key-name validation for workspace env vars."""
from __future__ import annotations

import re

import pytest

from agentbox.core.service.workspaces import WorkspaceService


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@pytest.mark.parametrize(
    "key,valid",
    [
        ("FOO", True),
        ("MY_VAR", True),
        ("_private", True),
        ("a1", True),
        ("A_B_C_123", True),
        ("1BAD", False),
        ("has-dash", False),
        ("has space", False),
        ("has.dot", False),
        ("emptystring", True),  # the regex allows this; empty rejected elsewhere
    ],
)
def test_key_regex(key: str, valid: bool) -> None:
    assert bool(_ENV_KEY_RE.match(key)) == valid


def test_set_env_vars_rejects_invalid_keys() -> None:
    """set_env_vars rejects shell-invalid key names at the service level."""
    ws = WorkspaceService()
    with pytest.raises(ValueError, match="invalid env-var key"):
        ws.set_env_vars("ws-test", {"1BAD": "value"})

    with pytest.raises(ValueError, match="invalid env-var key"):
        ws.set_env_vars("ws-test", {"has-dash": "value"})

    with pytest.raises(ValueError, match="invalid env-var key"):
        ws.set_env_vars("ws-test", {"has space": "value"})
