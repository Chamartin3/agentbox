"""Seed default runner profiles on startup.

Idempotent: skips profiles whose ID already exists. Called from the
FastAPI startup hook so a fresh DB always has usable defaults wired to
the unified ``token`` backend.
"""

from __future__ import annotations

import json as _json
import logging

from agentbox.core.config import load_settings
from agentbox.core.constants import BackendName
from agentbox.core.db.database import get_database
from agentbox.core.data import RunnerProfileCreate
from agentbox.core.db.utils import now_iso

_log = logging.getLogger(__name__)


# Stable IDs so re-running startup is a no-op.
DEFAULT_PROFILES: list[RunnerProfileCreate] = [
    RunnerProfileCreate(
        id="openai-default",
        name="OpenAI (default)",
        description="OpenAI GPT-4o via the token backend.",
        backend=BackendName.TOKEN,
        provider="openai",
        model="openai:gpt-4o",
        api_key_env="OPENAI_API_KEY",
        is_enabled=True,
        is_system_default=True,
    ),
    RunnerProfileCreate(
        id="anthropic-default",
        name="Anthropic Claude",
        description="Anthropic Claude Sonnet via the token backend.",
        backend=BackendName.TOKEN,
        provider="anthropic",
        model="anthropic:claude-sonnet-4-6",
        api_key_env="ANTHROPIC_API_KEY",
        is_enabled=True,
    ),
    RunnerProfileCreate(
        id="google-gemini-default",
        name="Google Gemini",
        description="Google Gemini 2.0 Flash via the token backend.",
        backend=BackendName.TOKEN,
        provider="google",
        model="google:gemini-2.0-flash",
        api_key_env="GOOGLE_API_KEY",
        is_enabled=True,
    ),
    RunnerProfileCreate(
        id="ollama-local",
        name="Ollama (local)",
        description="Local Ollama via the token backend.",
        backend=BackendName.TOKEN,
        provider="ollama",
        model="ollama:llama3",
        base_url="http://localhost:11434",
        is_enabled=True,
    ),
    RunnerProfileCreate(
        id="grok-default",
        name="Grok (xAI)",
        description="xAI Grok via the token backend.",
        backend=BackendName.TOKEN,
        provider="xai",
        model="xai:grok-3",
        api_key_env="XAI_API_KEY",
        is_enabled=True,
    ),
    RunnerProfileCreate(
        id="qwen-via-openrouter",
        name="Qwen (OpenRouter)",
        description="Qwen 2.5 72B via OpenRouter, token backend.",
        backend=BackendName.TOKEN,
        provider="openrouter",
        model="openrouter:qwen/qwen-2.5-72b-instruct",
        api_key_env="OPENROUTER_API_KEY",
        is_enabled=True,
    ),
]


def seed_default_runner_profiles(store=None) -> int:  # store param kept for backward compat
    """Insert default runner profiles that don't already exist.

    Returns the number of profiles inserted. Errors on a single profile
    are logged and skipped so a malformed default never blocks startup.
    """
    db = get_database(str(load_settings().db_path))
    mgr = db.runner_profiles
    created = 0
    for spec in DEFAULT_PROFILES:
        assert spec.id is not None  # all defaults declare an id
        try:
            if mgr.get_by_id(spec.id) is not None:
                continue  # already exists
            now = now_iso()
            mgr.create_one(
                id=spec.id,
                name=spec.name,
                description=spec.description,
                backend=spec.backend,
                provider=spec.provider,
                model=spec.model,
                base_url=spec.base_url,
                api_key_env=spec.api_key_env,
                output_mode=spec.output_mode,
                params_json=_json.dumps(spec.params),
                headers_json=_json.dumps(spec.headers),
                extra_args_json=_json.dumps(spec.extra_args),
                is_enabled=int(spec.is_enabled),
                is_system_default=int(spec.is_system_default),
                created_at=now,
                updated_at=now,
            )
            created += 1
            _log.info("seeded default runner profile: %s", spec.id)
        except Exception as exc:
            _log.warning("failed to seed runner profile %s: %s", spec.id, exc)
    return created
