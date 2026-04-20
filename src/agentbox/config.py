"""Process-wide configuration, read from environment at import time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    project_root: Path
    port: int
    host: str
    workspaces_root: Path
    """Where per-agent workspaces live by default.

    Resolved from AGENTBOX_WORKSPACES_ROOT or
    `<project_root>/workdir/agentbox/workspaces`.
    """

    completion_webhook_url: str | None
    """Default webhook URL POSTed after every run finishes (success or error).

    Resolved from AGENTBOX_COMPLETION_WEBHOOK_URL. Per-agent override via
    AgentDef.webhook_url. If unset, no webhook is fired.
    """

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("AGENTBOX_DATA_DIR", "/data"))
    db_path = data_dir / "agentbox.sqlite"
    project_root = Path(os.environ.get("AGENTBOX_PROJECT_ROOT", "/project"))
    port = int(os.environ.get("AGENTBOX_PORT", "8765"))
    host = os.environ.get("AGENTBOX_HOST", "0.0.0.0")
    workspaces_root = Path(
        os.environ.get(
            "AGENTBOX_WORKSPACES_ROOT",
            str(project_root / "workdir" / "agentbox" / "workspaces"),
        )
    )
    completion_webhook_url = os.environ.get("AGENTBOX_COMPLETION_WEBHOOK_URL") or None
    return Settings(
        data_dir=data_dir,
        db_path=db_path,
        project_root=project_root,
        port=port,
        host=host,
        workspaces_root=workspaces_root,
        completion_webhook_url=completion_webhook_url,
    )


SETTINGS = load_settings()
