# Automate with webhooks

For a one-shot worker, polling is rarely desirable. Given a
`webhook_url`, the moment the run finishes AgentBox calls back with the
completed run: status, output, and usage. This is what turns AgentBox into a
multi-use agentic API: submit work, get the result pushed back.

## Set the webhook per run

```bash
curl -X POST http://localhost:8765/api/runs \
  -H 'content-type: application/json' \
  -d '{
    "agent": "research-analyst",
    "input": "Summarize this paper ...",
    "webhook_url": "https://your-service.example.com/hooks/agentbox"
  }'
```

## Or make it the agent default

Set a `webhook_url` on the agent itself and every run fires the webhook on
completion unless a request overrides it.

=== "Dashboard"

    Open the agent, go to the **Configuration** tab, and fill in the
    **webhook URL** field under execution settings (the same panel shown in
    [3. Managing agents](03-first-agent.md#composition)). Every run of the agent
    then calls back on completion.

=== "API"

    ```json title="agent config"
    { "webhook_url": "https://your-service.example.com/hooks/agentbox" }
    ```

## Delivery and verification

AgentBox POSTs the completed run payload to the target URL, with retries, and logs
each delivery (status, response, latency, error) so failed callbacks are
visible rather than silently lost.

To verify the payload really came from AgentBox, set a signing secret:

```bash title=".env"
AGENTBOX_WEBHOOK_SECRET=some-long-random-string
```

Deliveries are then signed with an HMAC the receiver can check before
trusting the body.

!!! tip "Local testing"
    Point `webhook_url` at a request-inspection endpoint (for example a local
    `nc -l 9000` or a tunnel to a dev server) to see the exact payload shape
    before wiring it into production.

---

Next: **[Evaluate & improve →](07-evaluate.md)**
