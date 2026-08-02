# Configuring a provider

Before an agent can run, AgentBox needs to know **what executes it** and **how
to authenticate**. Both live in one object: a **runner profile**. This step is
optional and depends on which model the agent uses. Only the profile that is
actually run needs to be configured.

## What a runner profile is

A runner profile is the thing an agent selects at run time. It composes three
parts:

- **Provider** (*who serves the model*): `openai`, `anthropic`, `google`,
  `xai`, `deepseek`, `openrouter`, `ollama`, …
- **Harness** (*how the model is driven*). The `token` harness calls the
  provider's API in-process. `claude_code`, `opencode`, `codex` and `pi` each
  drive a real CLI coding agent as a subprocess. (In the CLI this field is
  `--backend`.)
- **Model** (*which model* the harness asks the provider for). This is
  optional: when left off, the harness/provider picks.

`Provider + Harness + Model` + credentials = one runnable profile.

## Configure it in the dashboard

Open **Settings → Runners & credentials**. This is the fastest way to see the
whole picture: which harnesses are authenticated, which providers still need a
key, and the default model each harness uses.

<figure markdown>
  ![Runners & credentials in the dashboard](img/providers-settings.png)
  <figcaption>Settings → Runners & credentials: harness auth status, per-provider API-key state, and default models — all in one place.</figcaption>
</figure>

- **Harnesses** — each row shows its auth (`✓ login` or `⚠ login · missing`),
  compatible providers, and a default model that can be set inline.
- **Providers** — each shows whether its API key is present (`✓`) or missing
  (`⚠`); click **add** next to a provider to store its key from the browser.
- **Credentials** — the panel below lists what's already configured (from
  file/env or added in the UI); values are never shown back.

Manage the runner **profiles** themselves under **Runners** in the top nav —
add, edit, or remove the `Provider + Harness + Model` combinations agents
select at run time.

## Or manage profiles from the CLI

The same profiles live under `agentbox engine profile`:

```bash
docker compose exec agentbox agentbox engine profile ls
docker compose exec agentbox agentbox engine profile new \
  --id my-claude --name "Claude via CLI" \
  --backend claude_code --provider anthropic
```

!!! note "Starter profiles"
    A fresh instance seeds a handful of starter profiles so `run` works
    immediately. Treat them as examples, not recommendations. Use `engine
    profile rm` for the unwanted ones, and `new` for custom profiles.

## Three ways to authenticate

A harness doesn't carry its own credentials. They are supplied one of three
ways, and **which ways are available depends on the harness.**

!!! tip "In the dashboard"
    For plain **API tokens**, the quickest path is **Settings → Runners &
    credentials → add** next to the provider (shown above) — no shell needed.
    **Harness logins** (the OAuth flows below) are interactive and run in the
    box, so they stay on the CLI.

**1. API token**: a provider API key, read from an environment variable.
Prompt for and store one:

```bash
docker compose exec agentbox agentbox engine cred setup openai
# asks for OPENAI_API_KEY, writes it to the creds env file
```

**2. Harness login**: authenticate *inside the box* with the harness's own
OAuth flow. This uses an existing Claude / OpenCode / Codex subscription, so no
API key is needed:

```bash
docker compose exec -it agentbox agentbox engine cred setup claude_code
# runs `claude /login` interactively
```

**3. Imported credentials**: copy an existing login from the host machine
into the box, instead of logging in again:

```bash
docker compose exec agentbox agentbox engine cred import claude_code
# copies host ~/.claude/.credentials.json into the creds volume
```

Anything stored, whether env keys or OAuth tokens, lands under `creds/` in the
`agentbox-creds` volume, so it survives container recreation. Run `agentbox
engine cred setup` with **no argument** for an interactive walkthrough of every
harness, or `cred status` to see what's already configured.

### Which harness supports which

| Harness | API token | Harness login | Import host creds |
|---|---|---|---|
| `token` | ✅ provider key | ✗ | ✗ |
| `claude_code` | ✅ `ANTHROPIC_API_KEY` | ✅ `claude /login` | ✅ `~/.claude` |
| `opencode` | ✅ `OPENAI` / `OPENROUTER` key | ✅ `opencode login` | ✅ `~/.local/share/opencode/auth.json` |
| `codex` | ✅ `CODEX_API_KEY` / `OPENAI_API_KEY` | ✅ `codex login` | ✗ |
| `pi` | ✗ | ✅ `pi login` | ✗ |

## Provider-specific setup

Most providers are covered by the three methods above. Two cases need a little
more.

=== "API keys in bulk"

    To wire several `token`-harness providers at once, drop a `.env` next to
    `docker-compose.yml` with only the keys in use, then restart. Each seeded
    `token` profile reads its key from the matching variable:

    ```bash title=".env"
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    GOOGLE_API_KEY=...
    XAI_API_KEY=...
    OPENROUTER_API_KEY=...
    ```

    ```bash
    docker compose up -d agentbox   # restart to pick up the new env
    ```

=== "Ollama (no credentials)"

    This is the zero-credential path: run Ollama as a **sibling container** so
    nothing is installed on the host.

    **1. Add an Ollama service** with an override file:

    ```yaml title="docker-compose.override.yml"
    services:
      ollama:
        image: ollama/ollama
        volumes:
          - ollama:/root/.ollama
      agentbox:
        depends_on:
          - ollama
    volumes:
      ollama:
    ```

    **2. Start it and pull a model** (into the Ollama container):

    ```bash
    docker compose up -d
    docker compose exec ollama ollama pull llama3
    ```

    **3. Create a runner profile** pointing at the container. Compose services
    reach each other by name, so the base URL is `http://ollama:11434`:

    ```bash
    agentbox engine profile new \
      --id ollama --name "Ollama (container)" \
      --backend token --provider ollama \
      --model ollama:llama3 --base-url http://ollama:11434
    ```

!!! tip "Ollama on the host instead of a container"
    A seeded `ollama-local` profile targets `http://localhost:11434`. When
    Ollama runs on the host, the container rewrites `localhost` to
    `host.docker.internal` automatically. Override with
    `AGENTBOX_OLLAMA_URL_REWRITE=localhost=your-host` (empty string disables it).

---

Next: **[Agent →](03-first-agent.md)**
