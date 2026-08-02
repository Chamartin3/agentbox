# REST & WebSocket API

AgentBox exposes a REST API (plus one WebSocket stream) under `/api`, served on
port `8765`. The service is FastAPI, so an **interactive, always-current
reference** is generated live:

| URL | What |
|---|---|
| `/docs` | Swagger UI: try every endpoint in the browser |
| `/openapi.json` | Machine-readable OpenAPI schema |

Conventions used below: path parameters are in `{braces}`; all bodies are JSON
(`content-type: application/json`) unless noted; timestamps are ISO-8601
strings; a few stored fields (`composition_snapshot`, `variables`,
`validation_errors`) come back as **JSON-encoded strings**, not nested objects.

---

## Runs

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/runs` | Create a run (async; returns `run_id`) |
| `GET` | `/api/runs` | List runs; filters + pagination |
| `GET` | `/api/runs/_stats` | Aggregate run stats |
| `GET` | `/api/runs/_facets` | Available filter facets |
| `GET` | `/api/runs/{run_id}` | Fetch one run |
| `GET` | `/api/runs/{run_id}/prompt` | Assembled prompt, fragment by fragment |
| `GET` | `/api/runs/{run_id}/transcript` | Full transcript events |
| `WS` | `/api/runs/{run_id}/stream` | Live event stream (replays if finished) |
| `POST` | `/api/runs/{run_id}/cancel` · `/rerun` | Cancel / re-run |
| `POST` | `/api/runs/{run_id}/complete` · `/snapshot` · `/post_outcome` | Backend callbacks |
| `GET` `POST` | `/api/runs/{run_id}/comments` | List / add comments |
| `PUT` `DELETE` | `/api/runs/{run_id}/rating` | Set / clear a 0 to 5 rating |

### Create a run

`POST /api/runs`. Only `agent` is required; everything else is optional. `input`
drives a headless run; omit it for an interactive session. Pin execution with
`runner_profile` (or `backend`); otherwise the agent's bound profile, then the
system default, resolves it.

```json title="Request body"
{
  "agent": "research-analyst",
  "input": "Summarize this abstract on retrieval-augmented generation: ...",
  "runner_profile": "ollama",
  "variables": { "audience": "execs" },
  "workspace": "research",
  "timeout_seconds": 900,
  "webhook_url": "https://your-service.example.com/hooks/agentbox",
  "fresh_workspace": false,
  "session_mode": "headless"
}
```

| Field | Type | Notes |
|---|---|---|
| `agent` | string | **required**; agent id |
| `input` | string | Prompt input; omit for interactive |
| `variables` | object | `{{var}}` substitutions in the prompt |
| `session_id` | string | Resume an existing session |
| `workspace` | string | Named workspace; default is ephemeral |
| `timeout_seconds` | int | Per-run override of the agent's runner timeout |
| `webhook_url` | string | Completion callback for this run |
| `backend` | string | Force a backend (`opencode`, `claude_code`, ...) |
| `runner_profile` | string | Force a runner profile (wins over the agent's) |
| `runner_config` | object | Ad-hoc runner overrides |
| `fresh_workspace` | bool | Force a clean ephemeral workspace |
| `session_mode` | `"headless"` `"persistent"` | Run mode |

```json title="200 Response"
{ "run_id": "run-abc123", "agent": "research-analyst" }
```

Errors: `404` unknown agent · `403` `{"code":"agent_disabled",...}` · `422`
invalid input · `503` no backend available.


### Fetch a run

`GET /api/runs/{run_id}` → the run plus its usage.

```json title="200 Response"
{
  "run": {
    "id": "run-abc123",
    "agent_id": "research-analyst",
    "session_id": null,
    "status": "ok",
    "input": "Summarize this abstract ...",
    "output": "Summary: ...",
    "error": null,
    "created_at": "2026-08-02T10:15:04Z",
    "finished_at": "2026-08-02T10:15:12Z",
    "agent_version_id": 12,
    "runner_profile_id": "ollama",
    "validation_status": "ok",
    "validation_errors": null,
    "conversation_format": "opencode",
    "variables": "{\"audience\": \"execs\"}",
    "composition_snapshot": "{...}"
  },
  "usage": {
    "model": "ollama:llama3",
    "input_tokens": 4200,
    "output_tokens": 640,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "cost_usd": 0.0,
    "duration_ms": 8010
  }
}
```

`status` is one of `queued`, `running`, `ok`, `error`, `timeout`, `cancelled`.
`usage` is `null` until the backend reports it.

### List runs

`GET /api/runs` with query params: `agent`, `status`, `executor`, `agent_version`,
`q`, `since`, `until`, `limit` (default 50), `offset`, `paginated`.

```json title="200 Response (paginated=true)"
{
  "items": [
    {
      "id": "run-abc123",
      "agent_id": "research-analyst",
      "status": "ok",
      "created_at": "2026-08-02T10:15:04Z",
      "finished_at": "2026-08-02T10:15:12Z",
      "agent_version": 3,
      "reported_model": "ollama:llama3",
      "cost_usd": 0.0,
      "duration_ms": 8010,
      "rating": 4
    }
  ],
  "total": 1,
  "offset": 0,
  "limit": 50,
  "has_more": false
}
```

Without `paginated=true` the response is a bare array of the same items.

### Run stats

`GET /api/runs/_stats` (same filter params as list) → rollups.

```json title="200 Response"
{
  "totals": { "runs": 30, "input_tokens": 126000, "output_tokens": 19200, "cost_usd": 3.71, "avg_duration_ms": 8450 },
  "by_agent":  [ { "agent_id": "research-analyst", "runs": 30, "tokens": 145200, "cost_usd": 3.71 } ],
  "by_model":  [ { "model": "ollama:llama3", "runs": 18, "tokens": 80100, "cost_usd": 0.0 } ],
  "by_version":[ { "version": 3, "runs": 12, "tokens": 60000 } ],
  "by_status": [ { "status": "ok", "runs": 28 }, { "status": "error", "runs": 2 } ],
  "timeseries":[ { "bucket": "2026-08-01", "runs": 10, "cost_usd": 1.2 } ]
}
```

### Rate and comment

```json title="PUT /api/runs/{run_id}/rating"
{ "rating": 4 }
```

```json title="POST /api/runs/{run_id}/comments"
{ "author": "you@example.com", "body": "Good summary, missed one finding." }
```

```json title="Comment 200 Response"
{ "id": 7, "run_id": "run-abc123", "author": "you@example.com", "body": "Good summary, missed one finding.", "created_at": "2026-08-02T10:20:00Z" }
```

`DELETE /api/runs/{run_id}/rating` clears the rating.

### Stream a run

`WS /api/runs/{run_id}/stream`: connect and receive JSON events. Live while
running; replayed from the transcript if the run already finished.

```json title="Events (one JSON object per message)"
{"type": "thinking", "run_id": "run-abc123", "text": "Reading the abstract..."}
{"type": "tool_call", "tool": "fs.read", "arguments": {"path": "paper.md"}}
{"type": "text", "role": "assistant", "text": "Summary: ...", "delta": true}
{"type": "validation", "ok": true, "attempt": 1, "mode": "strict"}
{"type": "usage", "input_tokens": 4200, "output_tokens": 640, "cost_usd": 0.0}
{"type": "done", "ok": true, "status": "ok"}
```

Event `type`s: `text`, `thinking`, `tool_call`, `tool_result`, `usage`,
`validation`, `retry`, `timeout`, `log`, `done`.

---

## Agents

| Method | Path | Purpose |
|---|---|---|
| `GET` `POST` | `/api/agents` | List / create |
| `GET` `PATCH` `DELETE` | `/api/agents/{agent_id}` | Fetch / update / delete |
| `POST` | `/api/agents/{agent_id}/enable` · `/disable` | Toggle availability |
| `PATCH` | `/api/agents/{agent_id}/workspace` | Set workspace |
| `GET` `PATCH` `DELETE` | `/api/agents/{agent_id}/runner-profile` | Get / bind / unbind profile |
| `GET` `PUT` | `/api/agents/{agent_id}/validation` | Input & output validation |
| `GET` `PUT` | `/api/agents/{agent_id}/prompt` | Read / edit prompt |
| `GET` | `/api/agents/{agent_id}/prompt/versions[/{version}]` | Prompt versions |
| `POST` | `/api/agents/{agent_id}/prompt/rollback` | Roll back prompt |
| `GET` | `/api/agents/{agent_id}/versions[/{version}]` | Agent versions |
| `GET` | `/api/agents/{agent_id}/versions/{a}/diff/{b}` | Diff versions |
| `POST` | `/api/agents/{agent_id}/versions/{version}/rollback` · `/publish` | Roll back / publish |
| `POST` `DELETE` | `/api/agents/{agent_id}/versions/{version}/files[/{file_id}]` | Version files |
| `GET` `POST` `DELETE` | `/api/agents/{agent_id}/tool_grants[/{tool}]` | Tool grants |
| `POST` `DELETE` | `/api/agents/{agent_id}/forbidden_tools[/{tool}]` | Forbidden tools |
| `GET` | `/api/agents/{agent_id}/effective_tools` | Resolved allow/deny |
| `GET` | `/api/agent_tools[/{tool_name}]` | Discover tools |

### Create an agent

`POST /api/agents` → `201`. Required: `id`, `description`, `runner`, `author`,
`changelog` (≥3 chars). `runner` is a runner spec: pass `{}` for defaults.

```json title="Request body"
{
  "id": "research-analyst",
  "description": "Summarizes research papers into structured output",
  "prompt": "You are a research analyst. Produce a concise, structured summary.",
  "runner": { "timeout_seconds": 1200, "max_validation_retries": 2 },
  "composition": { "output_validation": "strict" },
  "tools": ["fs.read"],
  "tags": ["nlp", "analysis"],
  "webhook_url": null,
  "author": "you@example.com",
  "changelog": "initial draft"
}
```

```json title="201 Response"
{ "agent_id": "research-analyst", "version": 1, "version_id": 12 }
```

`409 {"code":"already_exists",...}` if the id is taken. Every edit creates a new
version; roll back with the version or prompt-rollback endpoints.

### Read / edit the prompt

```json title="GET /api/agents/{agent_id}/prompt → 200"
{ "path": "agents/research-analyst/system.md", "content": "You are a research analyst. ...", "size": 512, "mtime": "2026-08-02T10:00:00Z" }
```

```json title="PUT /api/agents/{agent_id}/prompt (request)"
{ "content": "You are a meticulous research analyst. ..." }
```

The `PUT` captures a new version only if the content changed (content-hash
dedup) and returns the same shape as `GET`.

```json title="POST /api/agents/{agent_id}/prompt/rollback (request)"
{ "target_version": 2, "author": "you@example.com" }
```

---

## Engines (backends, profiles, providers)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/runner-backends` | List backends |
| `GET` `POST` | `/api/runner-profiles` | List / create profiles |
| `GET` `PATCH` `DELETE` | `/api/runner-profiles/{profile_id}` | Fetch / update / delete |
| `GET` | `/api/runner-profiles/{profile_id}/stats` | Per-profile run stats |
| `GET` | `/api/runner-providers` | List providers |
| `POST` | `/api/runner-providers/refresh` | Refresh model cache |
| `GET` | `/api/runner-providers/{provider_id}/models` | List a provider's models |

`/api/providers/**` is an alias for `/api/runner-profiles/**`.

### Create a runner profile

`POST /api/runner-profiles`. Required: `name`, `backend`. `id` is optional (one
is generated if omitted). Local providers (Ollama) need no `api_key_env`.

```json title="Request body: containerized Ollama"
{
  "id": "ollama",
  "name": "Ollama (container)",
  "backend": "token",
  "provider": "ollama",
  "model": "ollama:llama3",
  "base_url": "http://ollama:11434",
  "is_enabled": true
}
```

```json title="201 Response (full profile)"
{
  "id": "ollama",
  "name": "Ollama (container)",
  "description": null,
  "backend": "token",
  "provider": "ollama",
  "model": "ollama:llama3",
  "base_url": "http://ollama:11434",
  "api_key_env": null,
  "output_mode": "auto",
  "params": {},
  "headers": {},
  "extra_args": [],
  "is_enabled": true,
  "is_system_default": false,
  "created_at": "2026-08-02T09:00:00Z",
  "updated_at": "2026-08-02T09:00:00Z"
}
```

`PATCH /api/runner-profiles/{id}` accepts any subset of the mutable fields
(`name`, `model`, `base_url`, `api_key_env`, `is_enabled`, `is_system_default`,
...) and returns the updated profile.

---

## Resources

| Method | Path | Purpose |
|---|---|---|
| `GET` `POST` | `/api/repo-resources` | List / create resources |
| `POST` | `/api/repo-resources/{resource_id}/versions/upload` | Upload a version (multipart) |
| `GET` | `/api/repo-resources/{resource_id}` · `/preview-modes` | Inspect |
| `DELETE` | `/api/repo-resources/{resource_id}` | Delete |
| `GET` `PUT` | `/api/agents/{agent_id}/prompt-resources` | List / bind prompt resources |
| `POST` | `/api/agents/{agent_id}/prompt-resources/preview` | Preview composed prompt |
| `GET` `PUT` | `/api/workspaces/{id}/resources` | List / bind workspace resources |

### Create and upload a resource

```json title="POST /api/repo-resources (request) → 201"
{ "slug": "research-guide", "type": "document", "display_name": "Research Guide", "tags": ["research"] }
```

Upload content as a **new version** with multipart form fields (`file`,
`changelog`, `actor`):

```bash
curl -X POST http://localhost:8765/api/repo-resources/research-guide/versions/upload \
  -F 'file=@./guidelines.md' \
  -F 'changelog=initial' \
  -F 'actor=you@example.com'
```

### Bind a resource into the prompt

`PUT /api/agents/{agent_id}/prompt-resources` replaces the agent's prompt
bindings. Put the `marker` (e.g. `{{GUIDELINES}}`) in the system prompt and the
resource is substituted at compose time.

```json title="Request body"
{
  "bindings": [
    { "resource_id": "research-guide", "marker": "{{GUIDELINES}}", "slot": "system", "mode": "inline", "required": true }
  ],
  "reason": "inline the research guide",
  "actor": "you@example.com"
}
```

`mode` is `inline` or `reference`; `slot` is the prompt slot (e.g. `system`).

---

<a id="workspace-mcp"></a>

## Workspaces

| Method | Path | Purpose |
|---|---|---|
| `GET` `POST` | `/api/workspaces` | List / create |
| `GET` `DELETE` | `/api/workspaces/by-name/{name}` | Fetch / delete |
| `GET` `PUT` | `/api/workspaces/by-name/{name}/permissions` | Permissions |
| `GET` | `/api/workspaces/by-name/{name}/mcp-tools` · `/skills[/{skill}]` | MCP tools / skills |
| `POST` | `/api/workspaces/by-name/{name}/generate-configs` · `/generate-skills` | Regenerate |
| `GET` `PUT` | `/api/workspaces/by-name/{name}/file` | Read / write a file |
| `GET` `PUT` | `/api/workspaces/{id}/resources` · `/subagents` · `/skill-bindings` | Bindings |
| `POST` | `/api/workspaces/{id}/resources/dry-run` | Preview a binding |
| `GET` `PUT` | `/api/workspaces/{id}/credentials` | Workspace credentials |
| `GET` | `/api/workspaces/{id}/available_tools` | Available tools |
| `GET` `PUT` `POST` | `/api/workspaces/{id}/env-doc[/preview]` | Env doc |
| `GET` | `/api/workspaces/{id}/mcp[/servers]` · `/mcp/policy` | Workspace MCP |
| `PUT` `DELETE` | `/api/workspaces/{id}/mcp/servers/{server_name}` | Add / remove MCP server |
| `PUT` | `/api/workspaces/{id}/mcp/policy` | Set tool policy |
| `POST` | `/api/workspaces/{id}/mcp/refresh` | Re-introspect |

### Create a workspace

```json title="POST /api/workspaces (request) → 201"
{ "name": "research", "description": "Persistent research workspace", "path": "/agentbox/workspaces/research" }
```

Omit `path` for a managed directory. `409` if the name already exists.

### Bind a resource into a workspace

`PUT /api/workspaces/{id}/resources` materializes a resource as a file on disk.

```json title="Request body"
{
  "bindings": [
    { "resource_id": "research-guide", "target_path": "docs/guidelines.md", "materialize_mode": "copy", "on_conflict": "overwrite" }
  ],
  "reason": "share the research guide",
  "actor": "you@example.com"
}
```

`materialize_mode`: `copy` · `symlink` · `mount`. `on_conflict`: `error` ·
`overwrite` · `skip`.

---

## Feedback & usage

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/activity/summary` · `/api/activity/runs` | Activity rollups |
| `GET` | `/api/usage` | Aggregate token / cost usage |

## System

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` · `/api/health` | Liveness |
| `GET` `PATCH` | `/api/settings[/{section}]` · `/deployment` · `/env-secrets` | Settings |
| `GET` `PUT` `POST` `DELETE` | `/api/project/mcp-servers[/{name}][/introspect]` | Project MCP servers |
| `GET` `POST` `PUT` `DELETE` | `/api/host-env/{capabilities,profiles}` | Host-env tools / profiles |
| `GET` `PUT` | `/api/agents/{agent_id}/host-env` | Agent host-env grants |
| `GET` | `/api/runs/{run_id}/host-env-calls` | Host-env call audit |
| `GET` `POST` `DELETE` | `/api/credentials[/{credential_id}]` | Stored credentials |
| `GET` | `/api/mcp/servers[/{name}/tools]` · `/groups` | Internal MCP inventory |

---

See also: **[CLI](reference-cli.md)** · **[MCP](reference-mcp.md)**.
