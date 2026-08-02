# Screenshots

Captures from the agentbox dashboard, used across the tutorial pages. The
dashboard ships a single **dark** theme, so all captures are dark. Target width
~1440px (captured at CSS scale). Keep them in this folder.

## Capture list

| File | Page(s) | What it shows |
|---|---|---|
| `dashboard-home.png` | 01-setup | Activity landing page — runs over time, failure rate, token/cost totals, per-action + per-model tables, recent-runs feed. |
| `providers-settings.png` | 02-providers | Settings → Runners & credentials — harness auth, per-provider key state, default models. |
| `agent-new.png` | 03-agent | The New Agent wizard (Identity → Runner → Prompt → Tools → Review). |
| `agents-list.png` | 03-agent | The Agents list — runner profile, workspace, version, run count per agent. |
| `agent-composition.png` | 03-agent | Composition tab of an agent with several resources bound, incl. the Live composed prompt chart (per-fragment share of the generated text). |
| `agent-config.png` | 03-agent, 06-webhooks | Agent Configuration tab — runner, workspace, execution limits, tool grant (Enabled vs Available), webhook URL. |
| `run-detail-transcript.png` | 03-agent | A run's Conversation tab — transcript, tool calls with args/results. |
| `run-prompt-fragments.png` | 03-agent | A run's assembled prompt, fragment by fragment with its source. |
| `agent-runner.png` | 04-structured-output | Runner step — `output_schema_path` and max validation retries. |
| `workspaces-list.png` | 05-workspaces | Workspaces list — file/skill/subagent/resource counts; + new workspace. |
| `workspace-detail.png` | 05-workspaces | Workspace detail — env docs, skills, subagents, scoped credentials, capabilities, MCP tools, file tree. |
| `run-rating.png` | 07-evaluate | A run with a 5-star rating in the header and a posted comment. |
| `version-stats.png` | 07-evaluate | Versions tab — per-version runs, avg rating, and comments. |
| `run-usage.png` | 08-compare | A run's usage panel — input/output/cache tokens and cost. |
| `dashboard-runs.png` | 08-compare | Runs page — model mix, token volume, status breakdown, per-run table with ratings. |
| `interactive-session.png` | 09-interactive | A run's live event stream (raw events) — text/tool/usage events over the WebSocket. |
