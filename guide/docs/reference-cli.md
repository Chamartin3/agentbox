# CLI

The `agentbox` CLI ships inside the image. Run it against the running service:

```bash
docker compose exec agentbox agentbox --help
docker compose exec agentbox agentbox <group> --help
```

Every command supports `--help`; that output is authoritative for flags. This
page is the command map.

## Top-level

| Command | Purpose |
|---|---|
| `agentbox run` | Run an agent, headless (`-p/--prompt`) or interactive (no prompt) |
| `agentbox agent` | Agent definitions, prompts, versions, tools, files |
| `agentbox work` | Workspaces, files, MCP, permissions, resources, skills |
| `agentbox engine` | Runner profiles, providers, backends, credentials |
| `agentbox system` | Env, health, host-env, MCP, project, settings |
| `agentbox ops` | Config, resources, work-env operations |
| `agentbox history` | Run history, logs, and stats |
| `agentbox mat` | Export / import agents between instances |

## `run`

```bash
agentbox run <agent> -p "prompt"              # headless
agentbox run <agent> --runner-profile ollama  # pick a profile (headless)
agentbox run <agent>                          # interactive TTY session
agentbox run --backend opencode -w research   # ad-hoc interactive, no agent
```

| Flag | Meaning |
|---|---|
| `-p, --prompt` | Prompt for a headless run (POST + stream) |
| `--headless` | Force headless mode |
| `-b, --backend` | Backend for an ad-hoc interactive session |
| `-w, --workspace` | Named workspace override |
| `--model` | Model override |
| `-e, --ephemeral` | Force a fresh ephemeral workspace |
| `--session-id` | Resume a session |

## `agent`

| Subgroup | Common commands |
|---|---|
| `agent def` | `new --name <id>` · `ls` · `show <id>` · `edit <id> --runner <profile>` |
| `agent prompt` | `edit <id>` · `log <id>` · `rollback <id> --to <n>` |
| `agent version` | `ls <id>` |
| `agent tool` | `ls <id>` · `grant <id> <tool>` |
| `agent files` | `add <id> --kind output_schema <path>` |
| `agent check` | Validate an agent definition |

## `work`

| Subgroup | Common commands |
|---|---|
| `work ws` | `new <name> --path <dir>` · `show` · `explore` · `shell` |
| `work file` | `gen <ws>` (regenerate backend config) |
| `work mcp` | `show <ws>` · `tools <ws>` |
| `work perm` | Workspace permissions |
| `work res` | Workspace resource bindings |
| `work skill` | Workspace skills |

## `engine`

| Subgroup | Common commands |
|---|---|
| `engine profile` | `ls` · `show <id>` · `new --id <id> --backend token --provider <p> --model <m> [--base-url <url>] [--api-key-env <VAR>]` · `delete <id>` |
| `engine provider` | `ls` · `models <provider> [--profile <id>]` · `refresh` |
| `engine backend` | `list` |
| `engine cred` | Manage stored credentials |

## `system`

| Subgroup | Purpose |
|---|---|
| `system health` | Service health check |
| `system settings` | Read / update settings sections |
| `system env` | Environment inspection |
| `system host` | Host-env profiles and grants |
| `system mcp` | Internal MCP inventory |
| `system project` | Project-level MCP servers |

## `history`

| Subgroup | Common commands |
|---|---|
| `history show <run-id>` | Run detail |
| `history log` | `comments <run-id>` |
| `history stat` | `usage --agent <id>` · `runs --range 30d --agent <id>` · `activity --range 30d` |

## `ops` · `mat`

| Command | Purpose |
|---|---|
| `ops resource repo` | `upload <slug> <path> --changelog <msg>` · `ls` · `show <slug>` · `rollback <slug> --version <n>` |
| `ops cfg` · `ops workenv` | Config and work-env operations |
| `mat export <agent> --to <dir>` | Export an agent (prompt, config, files) |
| `mat import <agent> --from <dir>` | Import an agent into this instance |

---

See also: **[REST & WebSocket API](reference-api.md)** · **[MCP](reference-mcp.md)**.
