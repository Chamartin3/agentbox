"""Provider API-key credential registration.

Provider API keys are provider-domain concerns (unlike backend CLI
logins, which each backend package registers). deepseek/openrouter have
no adapter module, so this central provider table keeps them.
"""

from __future__ import annotations

from agentbox.core.config import SETTINGS
from agentbox.core.engines.credentials.methods import Method
from agentbox.core.engines.credentials.registry import (
    CredentialMethod,
    CredentialState,
    _detect_env_var,
    register,
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
                    label=f"Set {_env_var} in {SETTINGS.creds_env_file}",
                    env_var=_env_var,
                ),
            ],
        )
    )
