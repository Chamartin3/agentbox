"""Process-wide configuration, read from environment at import time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_AGENTBOX_ROOT = Path("/agentbox")

# Hydrate os.environ from .env files so AGENTBOX_* and provider
# secrets (OPENROUTER_API_KEY, OLLAMA_HOST, …) can live in a file instead of
# being exported by hand. override=False → a real exported env var always wins;
# a missing file is a silent no-op. Runs once at import, before SETTINGS builds.
load_dotenv()  # nearest .env, walking up from cwd (dev convenience)
_creds_dir = os.environ.get("AGENTBOX_CREDS_DIR") or str(_AGENTBOX_ROOT / "creds")
load_dotenv(Path(_creds_dir) / ".env")  # designed secrets store (creds_env_file)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration derived from AGENTBOX_* environment variables.

    Required mounts (default to well-known paths when unset):
        project_root       →  /agentbox                    (AGENTBOX_ROOT_DIR)

    Optional mounts (default /dev/null when unset — missing is fine):
        agents_dir         →  /agentbox/agents.d        (AGENTBOX_AGENTS_DIR)
        prompts_dir        →  /agentbox/prompts.d        (AGENTBOX_PROMPTS_DIR)
        skills_dir         →  /agentbox/skills.d         (AGENTBOX_SKILLS_DIR)
        outputs_dir        →  /agentbox/outputs          (AGENTBOX_OUTPUTS_DIR)
        agents_bundle_dir  →  /agentbox/agents_bundle.d  (AGENTBOX_AGENTS_BUNDLE_DIR)

    Named volumes (always present inside the container):
        data_dir           →  /data                      (AGENTBOX_DATA_DIR)
        workspaces_root    →  <project_root>/workspaces  (derived, not configurable)

    Credentials:
        creds_dir          →  /agentbox/creds            (AGENTBOX_CREDS_DIR)
        creds_env_file     →  <creds_dir>/.env           (derived)

    Server:
        host               →  0.0.0.0                    (AGENTBOX_HOST)
        port               →  8765                       (AGENTBOX_PORT)
        completion_webhook_url → None                    (AGENTBOX_COMPLETION_WEBHOOK_URL)
        webhook_secret     →  ""                          (AGENTBOX_WEBHOOK_SECRET)
        secret_key         →  None                        (AGENTBOX_SECRET_KEY)

    MCP:
        mcp_transport      →  stdio                       (AGENTBOX_MCP_TRANSPORT)
        mcp_host           →  0.0.0.0                     (AGENTBOX_MCP_HOST)
        mcp_port           →  8766                        (AGENTBOX_MCP_PORT)
        mcp_discovery_ttl  →  86400                       (AGENTBOX_MCP_DISCOVERY_TTL)

    Startup / lifecycle:
        import_on_start    →  False                       (AGENTBOX_IMPORT_ON_START)
        skip_default_profiles → False                     (AGENTBOX_SKIP_DEFAULT_PROFILES)
        skip_resource_import  → False                     (AGENTBOX_SKIP_RESOURCE_IMPORT)

    Misc:
        extra_skill_roots  →  ""                          (AGENTBOX_EXTRA_SKILL_ROOTS)
        keep_run_dirs      →  False                       (AGENTBOX_KEEP_RUN_DIRS)
        in_container       →  False                       (AGENTBOX_IN_CONTAINER)
        ollama_url_rewrite →  None                        (AGENTBOX_OLLAMA_URL_REWRITE)
    """

    # Static mount config — snapshotted at import (load_settings). These are
    # the fields the test helpers construct directly.
    data_dir: Path
    db_path: Path
    port: int
    host: str

    agents_dir: Path | None
    agents_bundle_dir: Path | None
    prompts_dir: Path | None
    skills_dir: Path | None
    outputs_dir: Path | None

    completion_webhook_url: str | None

    # Everything below is a *live* read from os.environ (a @property, not a
    # frozen field) so per-test monkeypatch.setenv / runtime overrides take
    # effect. The env name + default still live here once — call sites read
    # SETTINGS.<name> and never re-spell the env var.

    # Project root — the directory containing project-level config.
    # Defaults to /agentbox (the standard container mount point).
    @property
    def project_root(self) -> Path:
        """Directory used as the project root for workspace/config resolution."""
        return Path(os.environ.get("AGENTBOX_ROOT_DIR", str(_AGENTBOX_ROOT)))

    # Credentials
    @property
    def creds_dir(self) -> Path:
        return Path(os.environ.get("AGENTBOX_CREDS_DIR", str(_AGENTBOX_ROOT / "creds")))

    @property
    def creds_env_file(self) -> Path:
        return self.creds_dir / ".env"

    # Server
    @property
    def webhook_secret(self) -> str:
        return os.environ.get("AGENTBOX_WEBHOOK_SECRET", "")

    @property
    def secret_key(self) -> str | None:
        return os.environ.get("AGENTBOX_SECRET_KEY") or None

    # MCP
    @property
    def mcp_transport(self) -> str:
        return os.environ.get("AGENTBOX_MCP_TRANSPORT", "stdio")

    @property
    def mcp_host(self) -> str:
        return os.environ.get("AGENTBOX_MCP_HOST", "0.0.0.0")

    @property
    def mcp_port(self) -> int:
        return int(os.environ.get("AGENTBOX_MCP_PORT", "8766"))

    @property
    def mcp_discovery_ttl(self) -> int:
        return int(os.environ.get("AGENTBOX_MCP_DISCOVERY_TTL", "86400"))

    # Startup / lifecycle
    @property
    def import_on_start(self) -> bool:
        return _bool_env("AGENTBOX_IMPORT_ON_START")

    @property
    def skip_default_profiles(self) -> bool:
        return bool(os.environ.get("AGENTBOX_SKIP_DEFAULT_PROFILES"))

    @property
    def skip_resource_import(self) -> bool:
        return bool(os.environ.get("AGENTBOX_SKIP_RESOURCE_IMPORT"))

    @property
    def default_backend(self) -> str:
        """Terminal fallback backend when no runner profile resolves.

        The single source of truth for an agent's backend is the runner
        profile cascade (per-run override → per-run profile → agent-bound
        profile → system-default profile). This settings value is the last
        resort below all of those — it replaced the legacy per-agent
        ``runner.kind``. Overridable via ``AGENTBOX_DEFAULT_BACKEND``.
        """
        return os.environ.get("AGENTBOX_DEFAULT_BACKEND", "token")

    # Backend default models — the fallback model a backend uses when the
    # runner config omits one. Overridable per backend via AGENTBOX_*_MODEL.
    # ``None`` means "let the backend's own CLI/SDK pick its default".
    @property
    def opencode_model(self) -> str:
        return os.environ.get("AGENTBOX_OPENCODE_MODEL", "opencode/deepseek-v4-flash-free")

    @property
    def codex_model(self) -> str | None:
        return os.environ.get("AGENTBOX_CODEX_MODEL") or None

    @property
    def pi_model(self) -> str | None:
        return os.environ.get("AGENTBOX_PI_MODEL") or None

    # Misc
    @property
    def extra_skill_roots(self) -> str:
        return os.environ.get("AGENTBOX_EXTRA_SKILL_ROOTS", "")

    @property
    def keep_run_dirs(self) -> bool:
        return _bool_env("AGENTBOX_KEEP_RUN_DIRS")

    @property
    def in_container(self) -> bool:
        return _bool_env("AGENTBOX_IN_CONTAINER")

    @property
    def ollama_url_rewrite(self) -> str | None:
        # None = unset; "" = explicitly disabled; "<map>" = rewrite rules
        return os.environ.get("AGENTBOX_OLLAMA_URL_REWRITE")

    @property
    def resource_cache_dir(self) -> Path:
        custom = os.environ.get("AGENTBOX_RESOURCE_CACHE_DIR")
        return Path(custom) if custom else self.data_dir / "resource_cache"

    @property
    def consumer_project_root(self) -> Path:
        return Path(os.environ.get("AGENTBOX_PROJECT_ROOT", "/project"))

    @property
    def workspaces_root(self) -> Path:
        """Per-agent workspace directories, backed by the agentbox-workspaces named volume."""
        return self.project_root / "workspaces"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def runs_tmpfs_dir(self) -> Path:
        preferred = Path("/run/agentbox")
        try:
            preferred.mkdir(parents=True, exist_ok=True)
            test_file = preferred / ".writable_test"
            test_file.write_bytes(b"")
            test_file.unlink()
            return preferred
        except OSError:
            return self.data_dir / "runs"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def mcp_cache_dir(self) -> Path:
        return self.data_dir / "mcp_cache"


def _optional_dir(env: str, default: str | None = None) -> Path | None:
    val = os.environ.get(env, default)
    if not val or val in {"/dev/null", ""}:
        return None
    return Path(val)


def _bool_env(env: str, default: bool = False) -> bool:
    val = os.environ.get(env, "").lower()
    return val in {"1", "true", "yes"} if val else default


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("AGENTBOX_DATA_DIR", "/data"))
    db_path = data_dir / "agentbox.sqlite"
    port = int(os.environ.get("AGENTBOX_PORT", "8765"))
    host = os.environ.get("AGENTBOX_HOST", "0.0.0.0")
    completion_webhook_url = os.environ.get("AGENTBOX_COMPLETION_WEBHOOK_URL") or None

    agents_dir = _optional_dir("AGENTBOX_AGENTS_DIR")
    agents_bundle_dir = _optional_dir("AGENTBOX_AGENTS_BUNDLE_DIR")
    prompts_dir = _optional_dir("AGENTBOX_PROMPTS_DIR")
    skills_dir = _optional_dir("AGENTBOX_SKILLS_DIR")
    outputs_dir = _optional_dir("AGENTBOX_OUTPUTS_DIR")

    return Settings(
        data_dir=data_dir,
        db_path=db_path,
        port=port,
        host=host,
        agents_dir=agents_dir,
        agents_bundle_dir=agents_bundle_dir,
        prompts_dir=prompts_dir,
        skills_dir=skills_dir,
        outputs_dir=outputs_dir,
        completion_webhook_url=completion_webhook_url,
    )


SETTINGS = load_settings()
