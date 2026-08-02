# Evaluate & improve

Every run is captured, so quality is something to measure, not guess. The loop
is: run it, score it, change one thing, and let the captured numbers show
whether the change helped.

## Score a run

Rate a run 0-5 and attach a comment.

=== "Dashboard"

    Open any run. Click the **star rating** in the header to score it 0-5, and
    add a note in the **Comments** box at the bottom. Both are saved instantly
    and roll up into the per-version stats.

    <figure markdown>
      ![Rating and commenting a run](img/run-rating.png)
      <figcaption>Scoring a run 0-5 with a comment, so quality becomes measurable.</figcaption>
    </figure>

=== "API"

    ```bash
    # Set a 0-5 rating
    curl -X PUT http://localhost:8765/api/runs/run-abc123/rating \
      -H 'content-type: application/json' \
      -d '{"rating": 4}'

    # Add a comment
    curl -X POST http://localhost:8765/api/runs/run-abc123/comments \
      -H 'content-type: application/json' \
      -d '{"author": "you@example.com", "body": "Good summary, missed one finding."}'
    ```

    Clear a rating with `DELETE /api/runs/run-abc123/rating`.

=== "CLI"

    ```bash
    agentbox history show run-abc123
    agentbox history log comments run-abc123
    ```

## Track quality across versions

Ratings and usage roll up per agent version. After a prompt changes or a
resource is swapped, comparing versions shows whether average quality, tokens, or time
moved:

```bash
agentbox agent version ls research-analyst
agentbox history stat stats --agent research-analyst
```

<figure markdown>
  ![Per-version stats](img/version-stats.png)
  <figcaption>Average rating, tokens, and time per agent version. Did the last change help?</figcaption>
</figure>

## Improve by adding and sharing resources

Most improvements are a prompt change or a better resource. The resource loop:

1. **Create / upload** a resource (document, schema, script, or skill):

    ```bash
    agentbox ops resource repo upload analysis-rubric ./rubric.md --changelog "v1"
    ```

2. **Bind** it to the workspace (a file on disk) or the prompt (inlined, see
   [adding resources](03-first-agent.md#attach-resources)):

    ```bash
    agentbox agent prompt edit research-analyst
    ```

3. **Reuse** the same resource in another agent by binding the same
   `resource_id`. One source of truth; a single update propagates to every agent that binds
   it too.

Scripts bound as resources can be exposed to the agent as MCP tools, so a
resource is not only context. It can be capability.

!!! note "Prompt versioning"
    Prompt edits are versioned. Review history and revert if a change made
    things worse:

    ```bash
    agentbox agent prompt log research-analyst
    agentbox agent prompt rollback research-analyst --to 3
    ```

---

Next: **[Swap harnesses & compare →](08-compare.md)**
