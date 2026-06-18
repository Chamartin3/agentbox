"""Credential method types."""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox.config import SETTINGS


@dataclass
class Method:
    key: str
    label: str
    available_on_host: bool = False
    command: list[str] | None = None
    env_var: str | None = None
    host_source: str | None = None
    container_target: str | None = None
    provider: str | None = None

    def apply(self, ctx: dict[str, Any]) -> None:
        if self.key == "import_host" and self.host_source and self.container_target:
            _import_host_credential(self.host_source, self.container_target)
        elif self.key == "login" and self.command:
            _run_interactive_login(self.command, ctx.get("creds_base", str(SETTINGS.creds_dir)))
        elif self.key in ("env_file", "paste_key") and self.env_var:
            _prompt_and_store_env_key(self.env_var, ctx.get("env_file", str(SETTINGS.creds_env_file)))


def _import_host_credential(host_source: str, container_target: str) -> None:
    src_path = Path(os.path.expanduser(host_source))
    if not src_path.exists():
        raise FileNotFoundError(f"Host credential not found at {src_path}")
    if not src_path.is_file():
        raise IsADirectoryError(f"Host credential path is a directory: {src_path}")
    target = Path(container_target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, target)
    target.chmod(0o600)


def _run_interactive_login(command: list[str], creds_base: str) -> None:
    env = dict(os.environ)
    if creds_base:
        env.setdefault("CLAUDE_CONFIG_DIR", creds_base)
    subprocess.run(command, env=env, check=False)


def _prompt_and_store_env_key(env_var: str, env_file: str) -> None:
    key_value = getpass.getpass(f"Enter value for {env_var}: ").strip()
    if not key_value:
        raise ValueError(f"No value provided for {env_var}")
    _upsert_env_line(Path(env_file), env_var, key_value)
    os.environ[env_var] = key_value


def _upsert_env_line(env_path: Path, key: str, value: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}=") or line.startswith(f"{key} "):
                lines.append(f'{key}="{value}"')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'{key}="{value}"')
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
