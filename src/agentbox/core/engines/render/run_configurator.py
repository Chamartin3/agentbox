"""Idempotent run-directory generator.

RunConfigurator owns the entire run-directory content.  It runs before any
backend adapter and produces a well-known directory layout.  Backends are
reduced to "read this layout and produce argv/env".

Usage::

    configurator = RunConfigurator(project_root=Path("/app"))
    run_cfg = configurator.prepare_run_dir(
        workdir=Path("/data/workspaces/drafting"),
        agent=agent_def,
        backend="opencode",
        composed=ComposedMetadata(system="...", user="...", schema={...}),
    )
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentbox.core.data import AgentDef
from agentbox.core.engines.render.backends import get_generator
from agentbox.core.engines.render.backends.base import McpConfig
from agentbox.core.engines.render.prompt_composer import PromptComposer
from agentbox.core.engines.render.skills.filter import filter_skills_for_backend
from agentbox.core.resources.skills import discover_skills


@dataclass(frozen=True)
class ComposedMetadata:
    """Everything the composer produced for this run."""

    system: str
    user: str
    schema: dict[str, Any] | None = None
    schema_sha: str | None = None
    bundle_sha: str = ""
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunConfig:
    """Result of preparing a run directory."""

    run_dir: Path
    backend_dir: Path  # e.g. run_dir / "backends" / "opencode"
    prompt_dir: Path  # run_dir / "prompts"
    meta: dict[str, Any]  # Parsed .agentbox/meta.json
    is_fresh: bool  # True if we regenerated this run_dir


class RunConfigurator:
    """Idempotent run-directory generator with caching."""

    def __init__(
        self,
        project_root: Path,
        runs_tmpfs_dir: Path | None = None,
        *,
        max_cache_age_seconds: int = 300,
    ) -> None:
        self.project_root = project_root
        self.runs_tmpfs_dir = runs_tmpfs_dir or (project_root / "tmp" / "runs")
        self.max_cache_age_seconds = max_cache_age_seconds
        self._locks: dict[str, Any] = {}  # asyncio.Lock keyed by cache key

    def prepare_run_dir(
        self,
        workdir: Path,
        agent: AgentDef,
        backend: str,
        composed: ComposedMetadata,
        force: bool = False,
        mcp: McpConfig | None = None,
    ) -> RunConfig:
        """Ensure a run directory exists with all required backend configs.

        1. Compute cache key from (agent.id, bundle_sha, backend, variables).
        2. Check existing run directories for a matching cache key.
        3. If cache miss or force=True, generate fresh.
        4. Write prompts/ and backends/<backend>/.
        5. Write .agentbox/meta.json with cache key for future lookups.
        6. Return RunConfig.
        """
        cache_key = self._compute_cache_key(agent, backend, composed)
        run_dir = self._find_cached_run_dir(cache_key)

        is_fresh = False
        if run_dir is None or force:
            run_dir = self._create_run_dir()
            is_fresh = True

        # Even on cache hit we need to ensure the directory is complete
        # (in case something was partially written).
        self._ensure_layout(run_dir, workdir, agent, backend, composed, cache_key, mcp)

        return RunConfig(
            run_dir=run_dir,
            backend_dir=run_dir / "backends" / backend,
            prompt_dir=run_dir / "prompts",
            meta=self._read_meta(run_dir),
            is_fresh=is_fresh,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_cache_key(
        self,
        agent: AgentDef,
        backend: str,
        composed: ComposedMetadata,
    ) -> str:
        """Stable cache key for this run configuration."""
        data = {
            "agent_id": agent.id,
            "bundle_sha": composed.bundle_sha,
            "backend": backend,
            "variables": dict(sorted(composed.variables.items())),
            "runner": {
                "timeout_seconds": agent.runner.timeout_seconds,
                "model": agent.runner.model,
                "extra_args": agent.runner.extra_args,
            },
        }
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _find_cached_run_dir(self, cache_key: str) -> Path | None:
        """Look for an existing run directory with a valid cache key."""
        if not self.runs_tmpfs_dir.exists():
            return None
        for candidate in self.runs_tmpfs_dir.iterdir():
            if not candidate.is_dir():
                continue
            meta = self._read_meta(candidate)
            if meta.get("cache_key") != cache_key:
                continue
            created_at = meta.get("created_at", 0)
            if time.time() - created_at > self.max_cache_age_seconds:
                continue
            return candidate
        return None

    def _create_run_dir(self) -> Path:
        """Allocate a fresh run directory."""
        self.runs_tmpfs_dir.mkdir(parents=True, exist_ok=True)
        run_dir = self.runs_tmpfs_dir / uuid.uuid4().hex
        run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        return run_dir

    def _ensure_layout(
        self,
        run_dir: Path,
        workdir: Path,
        agent: AgentDef,
        backend: str,
        composed: ComposedMetadata,
        cache_key: str,
        mcp: McpConfig | None = None,
    ) -> None:
        """Write all files if they don't already exist."""
        # 1. Meta
        self._write_meta(run_dir, cache_key, agent, backend)

        # 2. Prompts
        prompts_dir = run_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        self._write_prompts(prompts_dir, composed)

        # 3. Skills (copy filtered skills into backend-native dirs)
        backend_dir = run_dir / "backends" / backend
        backend_dir.mkdir(parents=True, exist_ok=True)

        skills = discover_skills(workdir)
        backend_skills = filter_skills_for_backend(skills, backend)
        self._copy_skills(backend_dir, backend_skills)

        # 4. Backend-specific configs
        self._generate_backend_configs(backend_dir, backend, agent, composed, mcp)

    def _write_meta(
        self,
        run_dir: Path,
        cache_key: str,
        agent: AgentDef,
        backend: str,
    ) -> None:
        """Write .agentbox/meta.json."""
        meta_dir = run_dir / ".agentbox"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / "meta.json"
        if meta_path.exists():
            return
        meta = {
            "cache_key": cache_key,
            "agent_id": agent.id,
            "backend": backend,
            "created_at": time.time(),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _read_meta(self, run_dir: Path) -> dict[str, Any]:
        meta_path = run_dir / ".agentbox" / "meta.json"
        if not meta_path.exists():
            return {}
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_prompts(self, prompt_dir: Path, composed: ComposedMetadata) -> None:
        """Write the canonical prompt files via PromptComposer."""
        PromptComposer.write_prompts(prompt_dir, composed)

    def _copy_skills(self, backend_dir: Path, skills: list[Any]) -> None:
        """Copy filtered skills into the backend's skills/ directory."""
        skills_dir = backend_dir / "skills"
        if not skills:
            return
        skills_dir.mkdir(parents=True, exist_ok=True)
        for skill in skills:
            target = skills_dir / skill.name / "SKILL.md"
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(skill.content, encoding="utf-8")

    def _generate_backend_configs(
        self,
        backend_dir: Path,
        backend: str,
        agent: AgentDef,
        composed: ComposedMetadata,
        mcp: McpConfig | None = None,
    ) -> None:
        """Dispatch to per-backend generators."""

        generator = get_generator(backend)
        if generator is not None:
            generator.generate(backend_dir, agent, composed, mcp)
