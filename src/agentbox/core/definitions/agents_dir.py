"""Directory scanner for ``agents.d/`` — supports both ``.toml`` and ``.md``.

Walk order (deterministic, sorted by filename):
1. ``*.toml`` files → standalone TOML agents
2. ``*.md`` files → markdown-frontmatter agents
3. Subdirectories → legacy ``agent.toml`` + ``prompts/system.md`` pattern

Dotfiles and ``README.md`` are always ignored.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from agentbox.core.constants import RunnerKind
from agentbox.core.data.manifest import (
    AgentDef,
    AgentManifest,
    AgentSource,
    RunnerSpec,
)
from agentbox.core.definitions.markdown import load_markdown_agent

logger = logging.getLogger(__name__)

_SKIP = frozenset({".", "..", "README.md"})


def _build_runner_spec(rm: Any) -> RunnerSpec:
    """Build a ``RunnerSpec`` from a ``RunnerManifest`` (or ``None``).

    Deprecated path. The on-disk ``[runner]`` table is import-only;
    runtime config resolves from ``runner_profiles`` +
    ``agent_versions.config_json``. This shim exists so legacy TOML
    bundles still register correctly — the values feed the Phase 2
    backfill into ``config_json[execution|runtime|python]``.
    """
    if rm is None:
        return RunnerSpec(kind=RunnerKind.TOKEN, timeout_seconds=120)
    logger.debug(
        "agents_dir: ignoring TOML [runner] kind=%r at runtime; runner "
        "profile binding is authoritative",
        getattr(rm, "kind", None),
    )
    return RunnerSpec(
        kind=rm.kind,
        model=rm.model,
        mcp_config_path=rm.mcp_config_path,
        allowed_tools=rm.allowed_tools,
        extra_args=rm.extra_args,
        timeout_seconds=rm.timeout_seconds,
        agent_module=rm.agent_module,
        output_schema_path=rm.output_schema_path,
        max_validation_retries=rm.max_validation_retries,
    )


def _is_hidden(entry: Path) -> bool:
    return entry.name.startswith(".")


def scan_agents_dir(agents_d_path: Path) -> list[AgentDef]:
    """Scan ``agents_d_path`` and return all agents found.

    Supports:
    - ``*.toml`` — standalone TOML agent definitions
    - ``*.md`` — markdown-with-YAML-frontmatter agents
    - Subdirectories containing ``agent.toml`` (legacy format)

    Returns agents in sorted order (by filename, then directory name).
    """
    if not agents_d_path.is_dir():
        return []

    agents: list[AgentDef] = []

    # 1. *.toml files
    toml_files = sorted(
        p
        for p in agents_d_path.iterdir()
        if p.is_file() and p.suffix == ".toml" and not _is_hidden(p)
    )
    for p in toml_files:
        try:
            agent = _load_standalone_toml(p)
            if agent is not None:
                agents.append(agent)
        except Exception as exc:
            logger.warning("agents.d: skipping %s: %s", p.name, exc)

    # 2. *.md files
    md_files = sorted(
        p
        for p in agents_d_path.iterdir()
        if p.is_file()
        and p.suffix == ".md"
        and p.name not in _SKIP
        and not _is_hidden(p)
    )
    for p in md_files:
        try:
            agent = load_markdown_agent(p)
            agents.append(agent)
        except Exception as exc:
            logger.warning("agents.d: skipping %s: %s", p.name, exc)

    # 3. Legacy subdirectories with agent.toml
    dirs = sorted(
        p for p in agents_d_path.iterdir() if p.is_dir() and not _is_hidden(p)
    )
    for d in dirs:
        try:
            agent = _load_legacy_dir_agent(d)
            if agent is not None:
                agents.append(agent)
        except Exception as exc:
            logger.warning("agents.d: skipping dir %s: %s", d.name, exc)

    return agents


def _load_standalone_toml(path: Path) -> AgentDef | None:
    """Load a standalone ``.toml`` file as an agent definition."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    manifest = AgentManifest.model_validate(data)

    resolved_prompt: str | None = None
    if manifest.prompt_path is not None:
        resolved = (path.parent / manifest.prompt_path).resolve()
        if resolved.exists():
            resolved_prompt = str(resolved)
    else:
        default = path.parent / "prompts" / "system.md"
        if default.exists():
            resolved_prompt = str(default)

    return AgentDef(
        id=manifest.id,
        description=manifest.description,
        prompt_path=resolved_prompt,
        composition=manifest.composition,
        workspace=manifest.workspace or "default",
        session_mode=manifest.session_mode,
        webhook_url=manifest.webhook_url,
        tags=manifest.tags,
        runner=_build_runner_spec(manifest.runner),
        source_path=path,
        source_format=AgentSource.STANDALONE_TOML,
    )


def _load_legacy_dir_agent(agent_dir: Path) -> AgentDef | None:
    """Load a legacy ``agent.toml`` agent definition.

    A directory is treated as an agent ONLY when it carries an explicit
    ``agent.toml`` manifest. The previous fallback that auto-discovered
    any directory containing ``prompts/system.md`` produced ghost
    entries in the agents list — one per Python module directory under
    ``apps/cvman/ai/agents/<name>/`` (e.g. ``stage_draft_fixer``) — even
    though those directories exist to host Python imports, not to
    register agents. With ``agent_versions`` (DB) now being the source
    of truth, agents are created via the API or sync flow; bare
    directories must NOT spawn duplicate manifest rows that collide
    with the DB-backed dot-notation entries (``stage.draft_fixer``).
    """
    manifest_path = agent_dir / "agent.toml"
    if not manifest_path.exists():
        return None

    with manifest_path.open("rb") as f:
        data = tomllib.load(f)
    manifest = AgentManifest.model_validate(data)

    if manifest.prompt_path is not None:
        resolved_prompt: str | None = str(
            (agent_dir / manifest.prompt_path).resolve()
        )
    else:
        default = agent_dir / "prompts" / "system.md"
        resolved_prompt = str(default) if default.exists() else None

    return AgentDef(
        id=manifest.id,
        description=manifest.description,
        prompt_path=resolved_prompt,
        composition=manifest.composition,
        workspace=manifest.workspace or "default",
        session_mode=manifest.session_mode,
        webhook_url=manifest.webhook_url,
        tags=manifest.tags,
        runner=_build_runner_spec(manifest.runner),
        source_path=manifest_path,
        source_format=AgentSource.LEGACY_DIR,
    )
