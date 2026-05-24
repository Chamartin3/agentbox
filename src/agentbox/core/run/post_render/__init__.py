"""Post-materialization hooks for backend adapters.

After ``BackendAdapter.render()`` returns a :class:`RenderedConfig` and
the executor materialises it into ``run_dir``, the executor calls
:meth:`BackendAdapter.post_render`. The default implementation injects
the agentbox MCP servers (host-env, agent-tools) into the generated
``claude_mcp.json``; backends that don't consume MCP config files can
override to skip.

The helpers in :mod:`mcp_inject` are pure file operations — they take
already-resolved grants and write the MCP config. Grant resolution and
gating stay in the executor (which owns the store).
"""

from __future__ import annotations

from agentbox.core.run.post_render.mcp_inject import (
    inject_agent_tools_mcp,
    inject_host_env_mcp,
)

__all__ = ["inject_agent_tools_mcp", "inject_host_env_mcp"]
