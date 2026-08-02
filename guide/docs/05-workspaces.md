# Workspaces

A **workspace** is the sandboxed environment a run executes in. It holds the
files, tools, skills, and resources an agent is allowed to touch, and it is the
isolation boundary between one agent and another.

There are two kinds:

| Kind | Lifecycle | Use it for |
|---|---|---|
| **Ephemeral** | Created fresh per run, discarded after | One-shot workers, parallel experiments, reproducible clean runs |
| **Persistent** | Named, reused across runs | Iterative work, interactive sessions, carrying state forward |

## Manage workspaces in the dashboard

The **Workspaces** page lists every persistent workspace with its file, skill,
subagent, and resource counts. **+ new workspace** creates one; **delete**
removes it.

<figure markdown>
  ![The workspaces list](img/workspaces-list.png)
  <figcaption>Every persistent workspace with its contents at a glance; create one with + new workspace.</figcaption>
</figure>

Open a workspace to configure everything it grants a run — environment
documentation (rendered to `CLAUDE.md` / `AGENTS.md`), skills, subagents,
credentials (least-privilege secrets), capabilities (file write / network / MCP
servers and tools), and the files bound into it.

<figure markdown>
  ![A workspace detail page](img/workspace-detail.png)
  <figcaption>The workspace detail page: env docs, skills, subagents, scoped credentials, capabilities, MCP tool grants, and the file tree — the full isolation boundary in one place.</figcaption>
</figure>

The API and CLI below do the same things for scripting and automation.

## Run in an ephemeral environment

Ephemeral is the default when a workspace is not named, and it can be forced
explicitly. Nothing from a previous run leaks in.

=== "API"

    ```bash
    curl -X POST http://localhost:8765/api/runs \
      -H 'content-type: application/json' \
      -d '{
        "agent": "research-analyst",
        "input": "List the files you can see.",
        "runner_profile": "ollama",
        "fresh_workspace": true
      }'
    ```

    `fresh_workspace: true` forces a clean ephemeral workspace for this run.

=== "CLI"

    ```bash
    agentbox run research-analyst -p "List the files you can see." --ephemeral
    ```

Because each ephemeral run gets its own directory, two agents can work the same
base in parallel without colliding. Running the same POST twice yields two
independent workspaces and two independent transcripts.

## Create a persistent workspace

Name a workspace when state should survive across runs (an interactive
session, a checked-out repo, generated files worth inspecting).

=== "Dashboard"

    On the **Workspaces** page, click **+ new workspace**, give it a name, and
    open it to add files, skills, and credentials.

=== "CLI"

    ```bash
    # Create a workspace backed by a directory
    agentbox work ws new research --path /agentbox/workspaces/research

    # Inspect it
    agentbox work ws show research
    agentbox work ws explore research
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8765/api/workspaces \
      -H 'content-type: application/json' \
      -d '{"name": "research", "path": "/agentbox/workspaces/research"}'
    ```

Then target it on a run:

```bash
agentbox run research-analyst -p "Continue where we left off." --workspace research
```

!!! tip "Regenerate the workspace config"
    AgentBox writes backend-specific config (MCP config, permissions, skill
    placement) into the workspace. Regenerate it after changing bindings:

    ```bash
    agentbox work file gen research
    ```

## Bind a resource into a workspace

In [3. Managing agents](03-first-agent.md#attach-resources) a
resource was bound **into the prompt** (inlined). The other option is to place it as a
**file on disk** in the workspace: use this for schemas, scripts, or reference
files the agent should read at a path. This reuses the same `research-guide`
resource:

!!! tip "In the dashboard"
    Open the workspace and use **+ add resource** in the **Files** section to
    place a resource on disk, choosing its target path. The API call below is
    the scriptable equivalent.

```bash
curl -X PUT http://localhost:8765/api/workspaces/research/files \
  -H 'content-type: application/json' \
  -d '{
    "bindings": [
      {
        "resource_id": "research-guide",
        "target_path": "docs/guidelines.md",
        "materialize_mode": "copy",
        "on_conflict": "overwrite"
      }
    ],
    "reason": "share the research guide",
    "actor": "you@example.com"
  }'
```

| Field | Values | Meaning |
|---|---|---|
| `materialize_mode` | `copy`, `symlink`, `mount` | How the resource lands in the workspace |
| `on_conflict` | `error`, `overwrite`, `skip` | What to do if the target exists |

The same resource can be bound into many workspaces: that is how AgentBox *shares*
context across environments.

!!! warning "Isolation boundary"
    A workspace is filesystem-level scoping, **not** an OS-level sandbox. A
    backend with shell access can reach the host. See the
    [isolation note](01-setup-system.md#isolation).

---

Next: **[6. Automate with webhooks →](06-webhooks.md)**
