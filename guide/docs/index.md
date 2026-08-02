<p align="center" markdown>
  ![AgentBox](img/logo.svg){ width="320" }
</p>

<p align="center" markdown>
**Run reusable agents inside isolated, fully captured environments, with
granular control over the tools and resources each agent can use.**
</p>

AgentBox is an agent orchestration backend. An agent and the
resources it needs are defined once, run in a controlled environment scoped to exactly
the allowed tools, and returned as a complete capture of the run (transcript,
tokens, cost, timing, and tool calls) to inspect, score, and improve. The same
agent runs across any supported harness (Claude Code, OpenCode, Codex, Pi,
pydantic-ai) through one API.

It's built for platform and AI engineers embedding agents into their own
products, and for anyone who needs agent runs to be isolated, reproducible, and
measurable instead of ad hoc.

The guide has two parts. **Setup & configuration** gets AgentBox running and
pointed at a provider. **Usage** builds, runs, and improves agents.

## Setup & configuration

| Step | What happens |
|---|---|
| **[1. Setup](01-setup-system.md)** | Build the image, start the service, open the dashboard |
| **[2. Configuring a provider](02-setup-providers.md)** | Point AgentBox at Ollama, an API key, or a CLI backend; one runner profile |

## Usage

| Step | What happens |
|---|---|
| **[3. Managing agents](03-first-agent.md)** | Compose an agent from a prompt, resources, and schemas; versioning and run history |
| **[4. Structured output](04-structured-output.md)** | Enforce a JSON schema and retry on invalid output |
| **[5. Workspaces](05-workspaces.md)** | Ephemeral and persistent sandboxed environments |
| **[6. Work interactively](09-interactive.md)** | Drive a live, sandboxed session scoped to a chosen few agents |
| **[7. Automate with webhooks](06-webhooks.md)** | Push completed results to an external service |
| **[8. Evaluate & improve](07-evaluate.md)** | Score runs, track quality, add and reuse resources |
| **[9. Swap harnesses & compare](08-compare.md)** | Run one agent on many backends; compare tokens, time, quality |

## Reference

| Page | What |
|---|---|
| **[REST & WebSocket API](reference-api.md)** | Every endpoint, grouped; plus the live `/docs` and `/openapi.json` |
| **[CLI](reference-cli.md)** | The `agentbox` command map |
| **[MCP](reference-mcp.md)** | AgentBox's own MCP server and its tool catalog |

## Core concepts

| Concept | What it is |
|---|---|
| **[Agent](03-first-agent.md#create-the-agent)** | A named definition: a composed prompt, an optional output schema, and a runner profile. |
| **[Runner / backend](02-setup-providers.md#what-a-runner-profile-is)** | The harness that executes the agent: `claude_code`, `opencode`, `codex`, `pi`, or `token` (pydantic-ai, in process). |
| **[Workspace](05-workspaces.md)** | The isolated environment a run executes in. Ephemeral (fresh per run) or persistent (reused). |
| **[Resource](03-first-agent.md#attach-resources)** | A typed input placed into a workspace or prompt: text document, JSON schema, script, or skill. |
| **[Run](03-first-agent.md#run-history)** | One execution of an agent, captured in full: transcript, usage, timing, tool calls. |

---

Start with **[1. Setup →](01-setup-system.md)**
