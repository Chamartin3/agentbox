"""Process-wide configuration, read from environment at import time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_AGENTBOX_ROOT = Path("/agentbox")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration derived from AGENTBOX_* environment variables.

    Required mount (must exist at startup):
        manifest_path  →  /agentbox/manifest.toml  (AGENTBOX_MANIFEST)

    Optional mounts (default /dev/null when unset — missing is fine):
        agents_dir     →  /agentbox/agents.d        (AGENTBOX_AGENTS_DIR)
        prompts_dir    →  /agentbox/prompts.d        (AGENTBOX_PROMPTS_DIR)
        skills_dir     →  /agentbox/skills.d         (AGENTBOX_SKILLS_DIR)
        outputs_dir    →  /agentbox/outputs          (AGENTBOX_OUTPUTS_DIR)

    Named volumes (always present inside the container):
        data_dir       →  /data                      (AGENTBOX_DATA_DIR)
        workspaces_root→  <project_root>/workspaces  (derived, not configurable)
    """

    manifest_path: Path
    data_dir: Path
    db_path: Path
    port: int
    host: str

    agents_dir: Path | None
    prompts_dir: Path | None
    skills_dir: Path | None
    outputs_dir: Path | None

    completion_webhook_url: str | None

    @property
    def project_root(self) -> Path:
        """Directory containing the manifest — /agentbox when using the standard mount."""
        return self.manifest_path.parent

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

    def check_manifest(self) -> None:
        """Raise RuntimeError with a clear message if the manifest is missing.

        Called at app startup so operators learn immediately when the required
        bind mount is absent or misconfigured.
        """
        if not self.manifest_path.exists():
            raise RuntimeError(
                f"agentbox cannot start: manifest not found at {self.manifest_path}.\n"
                "Ensure AGENTBOX_MANIFEST points to an agentbox.toml on the host and\n"
                "is bind-mounted into the container:\n"
                "  volumes:\n"
                "    - ${AGENTBOX_MANIFEST}:/agentbox/manifest.toml:ro"
            )


def _optional_dir(env: str, default: str | None = None) -> Path | None:
    val = os.environ.get(env, default)
    if not val or val in {"/dev/null", ""}:
        return None
    return Path(val)


def load_settings() -> Settings:
    manifest_path = Path(
        os.environ.get("AGENTBOX_MANIFEST", str(_AGENTBOX_ROOT / "manifest.toml"))
    )
    data_dir = Path(os.environ.get("AGENTBOX_DATA_DIR", "/data"))
    db_path = data_dir / "agentbox.sqlite"
    port = int(os.environ.get("AGENTBOX_PORT", "8765"))
    host = os.environ.get("AGENTBOX_HOST", "0.0.0.0")
    completion_webhook_url = os.environ.get("AGENTBOX_COMPLETION_WEBHOOK_URL") or None

    agents_dir = _optional_dir("AGENTBOX_AGENTS_DIR")
    prompts_dir = _optional_dir("AGENTBOX_PROMPTS_DIR")
    skills_dir = _optional_dir("AGENTBOX_SKILLS_DIR")
    outputs_dir = _optional_dir("AGENTBOX_OUTPUTS_DIR")

    return Settings(
        manifest_path=manifest_path,
        data_dir=data_dir,
        db_path=db_path,
        port=port,
        host=host,
        agents_dir=agents_dir,
        prompts_dir=prompts_dir,
        skills_dir=skills_dir,
        outputs_dir=outputs_dir,
        completion_webhook_url=completion_webhook_url,
    )


SETTINGS = load_settings()
