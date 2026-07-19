"""Capture the prompt fragments assembled for a run.

The aim is to make a run's *effective* prompt inspectable in the UI: what the
user typed, what the runner injects (agent system prompt, MCP config, allowed
tools, argv), and what's added downstream by the underlying CLI (Claude Code
adds its own environment description and tool definitions that we cannot
inspect directly).

A fragment list is built before the runner executes and stored alongside the
run. Each fragment records `source` (who supplied the text) and `injected_by`
(what layer pushes it into the model context), so the UI can group them.

Moved out of ``core/agents/composition/capture.py`` (plan 120): fragment
capture is an execution-observability concern, not part of the agents domain.
"""

from __future__ import annotations

import contextlib
import json
import shlex
from dataclasses import asdict
from pathlib import Path

from agentbox.core.data import AgentDef
from agentbox.core.data.composition import ComposedPrompt, PromptFragment
from agentbox.core.data.constants import BackendName


def capture_fragments(
    *,
    agent: AgentDef,
    user_input: str,
    project_root: Path,
    argv: list[str] | None = None,
    composed: ComposedPrompt | None = None,
    backend: str | None = None,
) -> str:
    """Build prompt fragments and return them as a JSON string.

    The single public entry point: execution code calls this once and stores
    the result — it never imports the fragment-building internals directly.
    ``backend`` is the run's resolved backend (from the one runner resolver);
    it drives backend-specific fragments and their ``injected_by`` labels.
    """
    frags = build_fragments(
        agent=agent,
        user_input=user_input,
        project_root=project_root,
        argv=argv,
        composed=composed,
        backend=backend,
    )
    return fragments_to_json(frags)


def build_fragments(
    agent: AgentDef,
    user_input: str,
    project_root: Path,
    argv: list[str] | None = None,
    composed: ComposedPrompt | None = None,
    backend: str | None = None,
) -> list[PromptFragment]:
    frags: list[PromptFragment] = [
        PromptFragment(
            name="user_input",
            source="user",
            injected_by="agentbox",
            content=user_input,
        ),
    ]

    composed_system = composed.system_text if composed is not None else None
    if composed_system is not None:
        frags.append(
            PromptFragment(
                name="agent_system_prompt",
                source="agent_def",
                injected_by="agentbox",
                content=composed_system,
            )
        )
        composed_schema = composed.composed_schema if composed is not None else None
        if composed_schema is not None:
            frags.append(
                PromptFragment(
                    name="output_schema",
                    source="agent_def",
                    injected_by="agentbox",
                    content=json.dumps(composed_schema, indent=2),
                )
            )

    if backend == BackendName.CLAUDE_CODE:
        frags.extend(_claude_code_fragments(agent, project_root, argv))
    elif backend == BackendName.TOKEN:
        frags.append(
            PromptFragment(
                name="token_note",
                source="agentbox",
                injected_by=BackendName.TOKEN,
                content=(
                    "The pydantic-ai Agent assembles its own message list at "
                    "call time (system prompt registered in the Agent ctor, "
                    "tool definitions from the @agent.tool decorators, plus the "
                    "user input above). The exact final messages are not "
                    "captured here — inspect the Agent definition in code."
                ),
                inspectable=False,
            )
        )

    return frags


def _claude_code_fragments(
    agent: AgentDef,
    project_root: Path,
    argv: list[str] | None,
) -> list[PromptFragment]:
    spec = agent.runner
    out: list[PromptFragment] = []

    agents_config_path = getattr(spec, "agents_config_path", None)
    if agents_config_path:
        out.append(
            _read_file_fragment(
                name="agents_config",
                path=project_root / agents_config_path,
                source="project",
                injected_by="claude_cli",
            )
        )
    if spec.mcp_config_path:
        out.append(
            _read_file_fragment(
                name="mcp_config",
                path=project_root / spec.mcp_config_path,
                source="project",
                injected_by="claude_cli",
            )
        )
    settings_path = getattr(spec, "settings_path", None)
    if settings_path:
        out.append(
            _read_file_fragment(
                name="settings",
                path=project_root / settings_path,
                source="project",
                injected_by="claude_cli",
            )
        )
    if spec.allowed_tools:
        out.append(
            PromptFragment(
                name="allowed_tools",
                source="agent_def",
                injected_by="claude_cli",
                content="\n".join(spec.allowed_tools),
            )
        )
    if argv:
        out.append(
            PromptFragment(
                name="argv",
                source="agentbox",
                injected_by="claude_cli",
                content=shlex.join(argv),
            )
        )
    out.append(
        PromptFragment(
            name="claude_cli_envelope",
            source="claude_cli",
            injected_by="claude_cli",
            content=(
                "Claude CLI also injects an environment description (cwd, platform, "
                "git status, date), built-in tool definitions, and the MCP tool "
                "schemas resolved from mcp_config. These are not visible to "
                "agentbox — only their inputs (the configs above) are."
            ),
            inspectable=False,
        )
    )
    return out


def _read_file_fragment(
    *, name: str, path: Path, source: str, injected_by: str
) -> PromptFragment:
    try:
        content = path.read_text(encoding="utf-8")
        # Pretty-print JSON if it parses, to make the UI easier to read.
        if path.suffix == ".json":
            with contextlib.suppress(json.JSONDecodeError):
                content = json.dumps(json.loads(content), indent=2)
        return PromptFragment(
            name=name, source=source, injected_by=injected_by, content=content
        )
    except OSError as exc:
        return PromptFragment(
            name=name,
            source=source,
            injected_by=injected_by,
            content=f"<unreadable {path}: {exc}>",
            inspectable=False,
        )


def fragments_to_json(frags: list[PromptFragment]) -> str:
    return json.dumps(
        [{**asdict(f), "size_bytes": f.size_bytes} for f in frags],
        ensure_ascii=False,
    )


__all__ = [
    "build_fragments",
    "capture_fragments",
    "fragments_to_json",
]
