import { useState, useEffect } from "react";
import { apiRequest } from "../../api/http";

interface ToolInfo {
  name: string;
  description: string;
  capability: string;
  tags: string[];
}

interface Grant {
  tool_name: string;
  granted_at: string;
  granted_by: string | null;
  changelog: string;
}

interface Props {
  agentId: string;
}

export function AgentToolGrantsPicker({ agentId }: Props) {
  const [availableTools, setAvailableTools] = useState<ToolInfo[]>([]);
  const [activeGrants, setActiveGrants] = useState<Grant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedTool, setSelectedTool] = useState<string>("");
  const [grantReason, setGrantReason] = useState("");
  const [grantLoading, setGrantLoading] = useState(false);

  const [revokeReason, setRevokeReason] = useState<Record<string, string>>({});

  const refresh = async () => {
    setLoading(true);
    try {
      const [tools, grants] = await Promise.all([
        apiRequest<{ items: ToolInfo[] }>("/api/agent_tools"),
        apiRequest<{ items: Grant[] }>(`/api/agents/${agentId}/tool_grants`),
      ]);
      setAvailableTools(tools.items ?? []);
      setActiveGrants(grants.items ?? []);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [agentId]);

  const grantedNames = new Set(activeGrants.map((g) => g.tool_name));
  const ungrantedTools = availableTools.filter((t) => !grantedNames.has(t.name));

  const handleGrant = async () => {
    if (!selectedTool || grantReason.trim().length < 3) return;
    setGrantLoading(true);
    try {
      await apiRequest(`/api/agents/${agentId}/tool_grants`, {
        method: "POST",
        body: JSON.stringify({ tool_name: selectedTool, changelog: grantReason }),
      });
      setSelectedTool("");
      setGrantReason("");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setGrantLoading(false);
    }
  };

  const handleRevoke = async (toolName: string) => {
    const reason = revokeReason[toolName]?.trim();
    if (!reason || reason.length < 3) return;
    try {
      await apiRequest(
        `/api/agents/${agentId}/tool_grants/${toolName}`,
        {
          method: "DELETE",
          body: JSON.stringify({ changelog: reason }),
        },
      );
      setRevokeReason((prev) => ({ ...prev, [toolName]: "" }));
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  if (loading) return <div>Loading tool grants…</div>;

  return (
    <div className="agent-tool-grants">
      <h3>Shared Agent Tools</h3>
      {error && <div className="error">{error}</div>}

      <section>
        <h4>Active Grants ({activeGrants.length})</h4>
        {activeGrants.length === 0 && <p className="muted">No tools granted.</p>}
        {activeGrants.map((grant) => (
          <div key={grant.tool_name} className="grant-row">
            <span className="tool-name">{grant.tool_name}</span>
            <span className="grant-meta">
              granted {new Date(grant.granted_at).toLocaleDateString()}
              {grant.granted_by && ` by ${grant.granted_by}`}
            </span>
            <input
              type="text"
              placeholder="Reason to revoke (required)"
              value={revokeReason[grant.tool_name] ?? ""}
              onChange={(e) =>
                setRevokeReason((prev) => ({
                  ...prev,
                  [grant.tool_name]: e.target.value,
                }))
              }
            />
            <button
              onClick={() => handleRevoke(grant.tool_name)}
              disabled={
                (revokeReason[grant.tool_name]?.trim().length ?? 0) < 3
              }
            >
              Revoke
            </button>
          </div>
        ))}
      </section>

      {ungrantedTools.length > 0 && (
        <section>
          <h4>Grant a Tool</h4>
          <select
            value={selectedTool}
            onChange={(e) => setSelectedTool(e.target.value)}
          >
            <option value="">— select a tool —</option>
            {ungrantedTools.map((t) => (
              <option key={t.name} value={t.name} title={t.description}>
                {t.name}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Reason (required, min 3 chars)"
            value={grantReason}
            onChange={(e) => setGrantReason(e.target.value)}
          />
          <button
            onClick={handleGrant}
            disabled={
              !selectedTool || grantReason.trim().length < 3 || grantLoading
            }
          >
            {grantLoading ? "Granting…" : "Grant"}
          </button>
        </section>
      )}

      {ungrantedTools.length === 0 && availableTools.length === 0 && (
        <p className="muted">
          No shared tools are registered. Consumer apps register tools via the{" "}
          <code>agentbox.agent_tools</code> entry-point group.
        </p>
      )}
    </div>
  );
}
