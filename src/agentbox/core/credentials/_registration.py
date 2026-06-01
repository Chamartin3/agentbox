"""Backend credential self-registration."""

from __future__ import annotations

import os
from pathlib import Path

from agentbox.core.credentials.methods import Method
from agentbox.core.credentials.registry import (
    CredentialMethod,
    CredentialState,
    _detect_env_var,
    _detect_oauth,
    register,
)

_CREDS_BASE = Path(os.environ.get("AGENTBOX_CREDS_DIR", "/agentbox/creds"))


def _detect_claude() -> CredentialState:
    oauth_path = _CREDS_BASE / "claude" / "credentials.json"
    if oauth_path.exists():
        return _detect_oauth(str(oauth_path))
    home_path = Path(os.path.expanduser("~/.claude/credentials.json"))
    if home_path.exists():
        return _detect_oauth(str(home_path))
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend="claude",
        label="Claude Code",
        detect=_detect_claude,
        methods=[
            Method(
                key="import_host",
                label="Import host ~/.claude/credentials.json",
                available_on_host=True,
                host_source="~/.claude/credentials.json",
                container_target=str(_CREDS_BASE / "claude" / "credentials.json"),
            ),
            Method(
                key="login",
                label="Run `claude /login` interactively",
                command=["claude", "/login"],
            ),
        ],
    )
)


def _detect_opencode() -> CredentialState:
    oauth_path = _CREDS_BASE / "opencode" / "auth.json"
    if oauth_path.exists():
        return _detect_oauth(str(oauth_path))
    home_path = Path(os.path.expanduser("~/.local/share/opencode/auth.json"))
    if home_path.exists():
        return _detect_oauth(str(home_path))
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend="opencode",
        label="OpenCode",
        detect=_detect_opencode,
        methods=[
            Method(
                key="import_host",
                label="Import host ~/.local/share/opencode/auth.json",
                available_on_host=True,
                host_source="~/.local/share/opencode/auth.json",
                container_target=str(_CREDS_BASE / "opencode" / "auth.json"),
            ),
            Method(
                key="login",
                label="Run `opencode login` interactively",
                command=["opencode", "login"],
            ),
        ],
    )
)


def _detect_codex() -> CredentialState:
    config_path = Path(os.path.expanduser("~/.config/codex/credentials.json"))
    if config_path.exists():
        return _detect_oauth(str(config_path))
    if os.environ.get("CODEX_API_KEY"):
        return CredentialState.PRESENT
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend="codex",
        label="Codex CLI",
        detect=_detect_codex,
        methods=[
            Method(
                key="login",
                label="Run `codex login` interactively",
                command=["codex", "login"],
            ),
        ],
    )
)


def _detect_pi() -> CredentialState:
    config_path = Path(os.path.expanduser("~/.config/pi/credentials.json"))
    if config_path.exists():
        return _detect_oauth(str(config_path))
    session_path = Path(os.path.expanduser("~/.pi/session.json"))
    if session_path.exists():
        return _detect_oauth(str(session_path))
    return CredentialState.MISSING


register(
    CredentialMethod(
        backend="pi",
        label="pi CLI",
        detect=_detect_pi,
        methods=[
            Method(
                key="login",
                label="Run `pi login` interactively",
                command=["pi", "login"],
            ),
        ],
    )
)

_PROVIDERS = [
    ("openai", "OpenAI API Key", "OPENAI_API_KEY"),
    ("anthropic", "Anthropic API Key", "ANTHROPIC_API_KEY"),
    ("google", "Google API Key", "GOOGLE_API_KEY"),
    ("xai", "xAI API Key", "XAI_API_KEY"),
    ("deepseek", "DeepSeek API Key", "DEEPSEEK_API_KEY"),
    ("openrouter", "OpenRouter API Key", "OPENROUTER_API_KEY"),
]

for _backend, _label, _env_var in _PROVIDERS:

    def _make_detect(env: str = _env_var) -> CredentialState:
        return _detect_env_var(env)

    register(
        CredentialMethod(
            backend=_backend,
            label=_label,
            detect=_make_detect,
            methods=[
                Method(
                    key="env_file",
                    label=f"Set {_env_var} in /agentbox/creds/.env",
                    env_var=_env_var,
                ),
            ],
        )
    )
