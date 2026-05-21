"""Grant resolution + per-call permission checks for host-env capabilities."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agentbox.core.infra.host_env.capabilities import CAPABILITIES


class GrantViolation(Exception):
    """Raised when a capability call violates the effective grant."""


def _deep_merge(base: dict | None, overrides: dict | None) -> dict:
    """Recursive merge: lists in overrides replace lists in base; dicts merge."""
    out: dict[str, Any] = dict(base or {})
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def resolve_grants(
    profile_grants: dict | None, workspace_overrides: dict | None
) -> dict:
    """Effective grants = profile ⊕ workspace overrides + default-granted caps.

    Always-granted capabilities (``Capability.default_granted=True``) are
    added if absent so the resolver doesn't have to special-case them.
    """
    merged = _deep_merge(profile_grants, workspace_overrides)
    for name, cap in CAPABILITIES.items():
        if cap.default_granted and name not in merged:
            merged[name] = {}
    return merged


def _safe_resolve(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _path_within_allowlist(path: str, allowed: list[str]) -> bool:
    target = _safe_resolve(path)
    for root_str in allowed:
        root = _safe_resolve(root_str)
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def check_capability(grants: dict, capability: str, params: dict | None = None) -> None:
    """Raise ``GrantViolation`` if ``capability`` is not allowed by ``grants``.

    Validates per-capability constraints (path scoping, command allowlist,
    URL host allowlist, env-var allowlist). The caller is expected to have
    already authenticated; this only enforces the declarative grant.
    """
    if capability not in CAPABILITIES:
        raise GrantViolation(f"unknown capability {capability!r}")
    if capability not in grants:
        raise GrantViolation(f"capability {capability!r} not granted")
    grant = grants[capability] or {}
    params = params or {}

    if capability in {
        "fs.read",
        "fs.list",
        "fs.write",
        "git.status",
        "git.log",
        "git.diff",
    }:
        path = params.get("path")
        if not path:
            raise GrantViolation(f"{capability}: missing required 'path' param")
        allowed = grant.get("allowed_paths") or []
        if not allowed:
            raise GrantViolation(f"{capability}: no allowed_paths configured")
        if not _path_within_allowlist(path, allowed):
            raise GrantViolation(
                f"{capability}: path {path!r} not within allowed_paths"
            )
        if capability in {"fs.read", "fs.write"}:
            max_bytes = int(grant.get("max_bytes", 1_048_576))
            size = params.get("size_hint")
            if size is not None and int(size) > max_bytes:
                raise GrantViolation(
                    f"{capability}: size {size} exceeds max_bytes {max_bytes}"
                )

    elif capability == "shell.exec":
        cmd = params.get("cmd")
        if not cmd:
            raise GrantViolation("shell.exec: missing 'cmd' param")
        allowlist = grant.get("command_allowlist") or []
        if not allowlist:
            raise GrantViolation("shell.exec: no command_allowlist configured")
        if not any(re.fullmatch(pat, cmd) for pat in allowlist):
            raise GrantViolation(f"shell.exec: command {cmd!r} not on allowlist")

    elif capability == "http.fetch":
        url = params.get("url")
        if not url:
            raise GrantViolation("http.fetch: missing 'url' param")
        host = urlparse(url).hostname or ""
        host_allow = grant.get("host_allowlist") or []
        if not host_allow:
            raise GrantViolation("http.fetch: no host_allowlist configured")
        if host not in host_allow:
            raise GrantViolation(f"http.fetch: host {host!r} not allowlisted")
        method = (params.get("method") or "GET").upper()
        methods = [m.upper() for m in (grant.get("methods") or ["GET"])]
        if method not in methods:
            raise GrantViolation(f"http.fetch: method {method!r} not allowed")

    elif capability == "env.get":
        name = params.get("name")
        if not name:
            raise GrantViolation("env.get: missing 'name' param")
        allow = grant.get("allowlist") or []
        if name not in allow:
            raise GrantViolation(f"env.get: var {name!r} not allowlisted")
        # Note: caller actually reads os.environ; we just authorize here.
        _ = os.environ.get(name)
