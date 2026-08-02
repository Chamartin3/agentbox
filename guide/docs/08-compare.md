# Swap harnesses & compare

Because an agent is composed from a prompt, resources, and a schema, the
definition is independent of the harness that runs it. The same
`research-analyst` runs on OpenCode today and Claude Code tomorrow: only the
backend changes. And because every run is captured with tokens, cost, and
timing, AgentBox can compare those harnesses head to head.

## Swap the backend per run

No edit to the agent needed. Override `backend` (and optionally `model`) on the
run:

=== "OpenCode"

    ```bash
    curl -X POST http://localhost:8765/api/runs \
      -H 'content-type: application/json' \
      -d '{"agent": "research-analyst", "input": "Summarize ...", "backend": "opencode"}'
    ```

=== "Claude Code"

    ```bash
    curl -X POST http://localhost:8765/api/runs \
      -H 'content-type: application/json' \
      -d '{"agent": "research-analyst", "input": "Summarize ...", "backend": "claude_code"}'
    ```

=== "CLI"

    ```bash
    agentbox run research-analyst -p "Summarize ..." --backend opencode
    ```

!!! note "Cloud backends need credentials"
    OpenCode, Claude Code, Codex, and Pi run their own CLIs and need provider
    credentials. Set them up once: see [Configuring a provider](02-setup-providers.md).

Same prompt, same schema, same resources, but a different executor. The captured
run records which `backend` and `reported_model` actually ran.

### What carries across, and what to check

| Element | Carries across backends? | Notes |
|---|---|---|
| Composed prompt | Yes | Assembled the same way regardless of backend |
| Output schema + validation | Yes | Enforced by AgentBox, not the backend |
| Resources (documents, schemas) | Yes | Bound to the workspace/prompt, backend-independent |
| Skills | Yes | Placed where each backend auto-discovers them (`.claude/`, `.opencode/`, ...) |
| MCP tools | Yes, if the backend supports MCP | `claude_code`, `opencode`, `token` support MCP; `codex` and `pi` are limited |
| Native tool names | Check | Each backend exposes its own native tools; keep `allowed_tools` portable |
| Model | Backend-specific | A model alias valid for one provider is not valid for another |

!!! tip "Mark backends an agent should skip"
    ```toml
    [agent]
    unsupported_backends = ["codex", "pi"]
    ```

## Compare tokens, time, and quality

Run the identical input on each backend, then compare the captured runs.

```bash
for be in opencode claude_code codex; do
  curl -s -X POST http://localhost:8765/api/runs \
    -H 'content-type: application/json' \
    -d "{\"agent\": \"research-analyst\", \"input\": \"Summarize the RAG paper.\", \"backend\": \"$be\"}"
done
```

!!! tip "In the dashboard"
    The **Runs** page is built for exactly this comparison. Filter to one agent,
    then read the **Model Mix**, **Token Volume**, and **Status Breakdown**
    charts and the per-run table (status, duration, tokens, rating side by side)
    to see which backend won — no scripting required.

    <figure markdown>
      ![The Runs page with comparison charts](img/dashboard-runs.png)
      <figcaption>The Runs page: model mix, token volume, status breakdown, and a per-run table with inline ratings — the visual side of the comparison below.</figcaption>
    </figure>

Rate each finished run 0-5 (see [Evaluate & improve](07-evaluate.md#score-a-run)). Every run
exposes the relevant fields on `GET /api/runs/{id}`:

| Field | Meaning |
|---|---|
| `backend` / `reported_model` | Which harness and model actually ran |
| `usage.input_tokens` / `output_tokens` | Prompt and completion tokens |
| `usage.cache_read_tokens` / `cache_write_tokens` | Prompt-cache activity |
| `usage.cost_usd` | Computed cost of the run |
| `usage.duration_ms` | Wall-clock time |
| `rating` | The 0-5 quality score |

<figure markdown>
  ![Run usage panel](img/run-usage.png)
  <figcaption>The usage panel: input/output/cache tokens and cost for one run.</figcaption>
</figure>

### Group the numbers by backend

```bash
curl -s "http://localhost:8765/api/runs?agent=research-analyst&limit=200&paginated=true" \
  | jq '[.items[] | {backend, model: .reported_model, cost: .cost_usd, ms: .duration_ms, rating}]
        | group_by(.backend)
        | map({backend: .[0].backend,
               runs: length,
               avg_cost: (map(.cost // 0) | add / length),
               avg_ms:   (map(.ms // 0)   | add / length),
               avg_rating: (map(.rating // 0) | add / length)})'
```

```json title="Example result"
[
  {"backend": "claude_code", "runs": 10, "avg_cost": 0.021, "avg_ms": 7800, "avg_rating": 4.3},
  {"backend": "opencode",    "runs": 10, "avg_cost": 0.014, "avg_ms": 9100, "avg_rating": 3.8},
  {"backend": "codex",       "runs": 10, "avg_cost": 0.011, "avg_ms": 6400, "avg_rating": 3.5}
]
```

Now the trade-off is explicit: `claude_code` costs more but scores highest;
`codex` is cheapest and fastest but lower quality. Pick per workload.

### Aggregate rollups

=== "API"

    ```bash
    curl -s "http://localhost:8765/api/runs/_stats?agent=research-analyst&since=2026-07-01"
    ```

    ```json title="RunStatsRow"
    {
      "run_count": 30, "success_count": 28, "failure_count": 2,
      "avg_duration_ms": 8450, "total_input_tokens": 126000,
      "total_output_tokens": 19200, "total_cost_usd": 3.71, "distinct_models": 3
    }
    ```

=== "CLI"

    ```bash
    agentbox history stat usage --agent research-analyst
    agentbox history stat runs --range 30d --agent research-analyst
    agentbox history stat activity --range 30d --agent research-analyst
    ```

## Move an agent between AgentBox instances

Share the whole agent (prompt, config, and files) by exporting and importing:

```bash
# On the source instance
agentbox mat export research-analyst --to ./exported/research-analyst

# On the target instance
agentbox mat import research-analyst --from ./exported/research-analyst
```

Because skills, resources, and the schema all live outside the harness, "which
harness" becomes a runtime choice: exactly what is needed when a new backend
appears or a provider changes its pricing.

---

Next: **[Work interactively →](09-interactive.md)**
