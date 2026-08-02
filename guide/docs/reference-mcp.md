# MCP

AgentBox ships an **internal MCP server** that exposes its own operations
(agents, prompts, runs, feedback, and resources) as MCP tools. Any MCP
client (Claude Code, an agent, a custom harness) can point at it to drive AgentBox
programmatically over the Model Context Protocol.

This is distinct from the **external** MCP servers connected *into* a
workspace (see [Workspaces](05-workspaces.md) and the
[API](reference-api.md#workspace-mcp)); this page documents AgentBox's own
server.

## Run the server

The `agentbox-mcp` entry point ships in the image:

```bash
docker compose exec agentbox agentbox-mcp
```

Transport and bind are controlled by environment variables:

| Env var | Default | Purpose |
|---|---|---|
| `AGENTBOX_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `AGENTBOX_MCP_HOST` | `0.0.0.0` | Bind host (http transport) |
| `AGENTBOX_MCP_PORT` | `8766` | Bind port (http transport) |

The server is built with FastMCP under the name `agentbox`. Plugins can register
additional tools via the `agentbox.agent_tools` entry-point group.

## Tool catalog

### Runs

| Tool | Purpose |
|---|---|
| `list_runs` | List runs with filters |
| `get_run` | Fetch a run |
| `get_run_output` | Final output |
| `get_run_transcript` | Full transcript |
| `get_run_conversation` | Conversation-formatted view |
| `get_run_logs` | Log events |
| `get_run_errors` | Errors from a run |
| `get_run_usage` | Tokens / cost |
| `get_run_prompt_fragments` | Assembled prompt, per fragment |
| `get_run_time_remaining` | Time left on a running run |
| `get_run_webhook_deliveries` | Webhook delivery log |
| `list_run_comments` · `add_run_comment` | Read / add comments |

### Agents

| Tool | Purpose |
|---|---|
| `list_agents` · `search_agents` | Browse agents |
| `get_agent` | Fetch an agent |
| `list_agent_tags` | Known tags |
| `get_agent_prompt_fragments` | The agent's composed prompt fragments |
| `list_executors` | Available backends |

### Prompts

| Tool | Purpose |
|---|---|
| `get_prompt` · `edit_prompt` | Read / edit the system prompt |
| `preview_prompt` | Preview a composed prompt |
| `list_prompt_versions` | Version history |
| `get_prompt_diff` | Diff two versions |
| `rollback_prompt` · `promote_version` | Roll back / promote a version |

### Resources & bindings

| Tool | Purpose |
|---|---|
| `create_repo_resource` · `create_repo_resource_from_files` | Create resources |
| `get_prompt_resources` · `set_prompt_resources` | List / set prompt bindings |
| `bind_prompt_resource` · `unbind_prompt_resource` | Bind / unbind one resource |
| `set_workspace_resources` | Bind resources into a workspace |
| `build_workspace` · `dry_run_workspace_resources` | Build / preview a workspace |
| `set_mcp_policy` · `toggle_mcp_server` · `toggle_mcp_tool` | Manage workspace MCP |
| `render_env_doc` · `set_env_doc` | Workspace env doc |
| `set_host_env_grants` · `list_host_env_calls` | Host-env grants / audit |

### Feedback & stats

| Tool | Purpose |
|---|---|
| `add_agent_version_rating` · `list_agent_version_ratings` | Rate / list version ratings |
| `add_agent_version_comment` | Comment on a version |
| `list_agent_versions` | Version list |
| `agent_stats` · `activity_summary` · `aggregate_usage` | Rollups |

### Utility

| Tool | Purpose |
|---|---|
| `get_run_time_remaining` | (runs, above) |
| current time | `time` tool for clock-aware agents |

---

See also: **[REST & WebSocket API](reference-api.md)** · **[CLI](reference-cli.md)**.
