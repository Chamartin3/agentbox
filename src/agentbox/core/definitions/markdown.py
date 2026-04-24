"""Frontmatter loader/writer for markdown-based agent definitions.

Each markdown file under ``agents.d/`` is a single agent: YAML frontmatter
holds metadata, the body is the system prompt.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
from frontmatter.default_handlers import YAMLHandler

from agentbox.core.constants import RunnerKind
from agentbox.core.data.manifest import AgentDef, AgentSource, RunnerSpec


def _fm_field(metadata: dict, key: str, default=None):
    """Read a key from metadata, supporting both top-level and runner nested."""
    return metadata.get(key, default)


def load_markdown_agent(path: Path) -> AgentDef:
    """Parse a markdown file with YAML frontmatter into an ``AgentDef``.

    The frontmatter maps to ``AgentDef`` fields:
    ``id``, ``description``, ``workspace``, ``tools``, ``tags``,
    ``session_mode``, ``claude_agent``, ``headless``, ``webhook_url``,
    ``unsupported_backends``.

    Runner-specific fields live under a ``runner`` key in the frontmatter.
    The markdown body becomes ``prompt`` (not ``prompt_path``).
    """
    post = frontmatter.load(str(path))
    meta = dict(post.metadata)

    agent_id = meta.pop("id", None)
    if not agent_id or not isinstance(agent_id, str):
        raise ValueError(
            f"{path}: markdown frontmatter must contain a string 'id' field"
        )

    runner_data = meta.pop("runner", {}) or {}
    if not isinstance(runner_data, dict):
        runner_data = {}

    kind_str = runner_data.pop("kind", None)
    runner_kind = RunnerKind(kind_str) if kind_str else RunnerKind.PYDANTIC_AI

    runner = RunnerSpec(
        kind=runner_kind,
        model=runner_data.pop("model", None),
        mcp_config_path=runner_data.pop("mcp_config_path", None),
        allowed_tools=runner_data.pop("allowed_tools", None) or [],
        extra_args=runner_data.pop("extra_args", None) or [],
        timeout_seconds=runner_data.pop("timeout_seconds", 120),
        agent_module=runner_data.pop("agent_module", None),
        output_schema_path=runner_data.pop("output_schema_path", None),
        max_validation_retries=runner_data.pop("max_validation_retries", 0),
    )

    tools = meta.pop("tools", None) or []
    tags = meta.pop("tags", None) or []
    unsupported_backends = meta.pop("unsupported_backends", None) or []

    body = (post.content or "").strip()
    if meta.get("prompt"):
        body = meta.pop("prompt")
    elif meta.get("prompt_path"):
        resolved = path.parent / meta.pop("prompt_path")
        if resolved.exists():
            body = resolved.read_text(encoding="utf-8").strip()

    return AgentDef(
        id=str(agent_id),
        description=str(meta.pop("description", "")),
        prompt=body or None,
        workspace=meta.pop("workspace", None),
        session_mode=meta.pop("session_mode", "headless"),
        claude_agent=bool(meta.pop("claude_agent", True)),
        headless=bool(meta.pop("headless", False)),
        webhook_url=meta.pop("webhook_url", None),
        tools=tools,
        tags=tags,
        unsupported_backends=unsupported_backends,
        runner=runner,
        source_path=path,
        source_format=AgentSource.MARKDOWN,
    )


def write_markdown_agent(
    path: Path,
    agent: AgentDef,
    *,
    preserve_unknown_keys: bool = True,
    existing_metadata: dict | None = None,
) -> None:
    """Write an ``AgentDef`` as a markdown file with YAML frontmatter.

    Parameters
    ----------
    path:
        Destination file path.
    agent:
        The agent definition to serialize.
    preserve_unknown_keys:
        When *True* (default), any keys in ``existing_metadata`` that are
        not part of the standard schema are preserved (forward-compat).
    existing_metadata:
        The previous frontmatter dict, loaded via ``frontmatter.load()``.
        Only used when ``preserve_unknown_keys`` is *True*.
    """
    metadata: dict = {}

    if preserve_unknown_keys and existing_metadata:
        known = _known_frontmatter_keys()
        for k, v in existing_metadata.items():
            if k not in known:
                metadata[k] = v

    metadata["id"] = agent.id
    if agent.description:
        metadata["description"] = agent.description
    if agent.workspace:
        metadata["workspace"] = agent.workspace
    if agent.tools:
        metadata["tools"] = agent.tools
    if agent.tags:
        metadata["tags"] = agent.tags
    if agent.session_mode != "headless":
        metadata["session_mode"] = agent.session_mode
    if not agent.claude_agent:
        metadata["claude_agent"] = False
    if agent.headless:
        metadata["headless"] = True
    if agent.webhook_url:
        metadata["webhook_url"] = agent.webhook_url
    if agent.unsupported_backends:
        metadata["unsupported_backends"] = agent.unsupported_backends

    runner_meta: dict = {}
    r = agent.runner
    if r.kind != RunnerKind.PYDANTIC_AI:
        runner_meta["kind"] = str(r.kind)
    if r.model:
        runner_meta["model"] = r.model
    if r.timeout_seconds != 120:
        runner_meta["timeout_seconds"] = r.timeout_seconds
    if r.mcp_config_path:
        runner_meta["mcp_config_path"] = r.mcp_config_path
    if r.allowed_tools:
        runner_meta["allowed_tools"] = r.allowed_tools
    if r.extra_args:
        runner_meta["extra_args"] = r.extra_args
    if r.agent_module:
        runner_meta["agent_module"] = r.agent_module
    if r.output_schema_path:
        runner_meta["output_schema_path"] = r.output_schema_path
    if r.max_validation_retries:
        runner_meta["max_validation_retries"] = r.max_validation_retries
    if runner_meta:
        metadata["runner"] = runner_meta

    body = agent.prompt or ""
    if existing_metadata and preserve_unknown_keys:
        body = body or ""

    post = frontmatter.Post(body, **metadata)
    text = frontmatter.dumps(post, handler=_OrderedYAMLHandler())
    text = text.strip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class _OrderedYAMLHandler(YAMLHandler):
    """Custom YAML handler that preserves field order and sorts keys."""


def _known_frontmatter_keys() -> set[str]:
    return {
        "id",
        "description",
        "workspace",
        "tools",
        "tags",
        "session_mode",
        "claude_agent",
        "headless",
        "webhook_url",
        "unsupported_backends",
        "runner",
        "prompt",
        "prompt_path",
    }
