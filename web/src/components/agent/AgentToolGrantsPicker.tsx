import { useState, useEffect } from "react";
import { apiRequest } from "../../api/http";

interface CatalogItem {
  name: string;
  description: string;
  kind: string;
  server?: string;
  grant_schema?: Record<string, unknown>;
  resource_id?: string;
  target_path?: string;
}

interface Grant {
  tool_name: string;
  granted_at: string;
  granted_by: string | null;
  changelog: string;
}

interface Props {
  agentId: string;
  workspaceId: string | null;
}

export function AgentToolGrantsPicker({ agentId, workspaceId }: Props) {
  const [availableTools, setAvailableTools] = useState<CatalogItem[]>([]);
  const [activeGrants, setActiveGrants] = useState<Grant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedTool, setSelectedTool] = useState<string>("");
  const [grantReason, setGrantReason] = useState("");
  const [grantLoading, setGrantLoading] = useState(false);

  const [revokeReason, setRevokeReason] = useState<Record<string, string>>({});

  const catalogUrl = workspaceId
    ? `/api/workspaces/${workspaceId}/available_tools`
    : "/api/agent_tools";

  const refresh = async () => {
    setLoading(true);
    try {
      const [catalog, grants] = await Promise.all([
        apiRequest<{ items: CatalogItem[] }>(catalogUrl),
        apiRequest<{ items: Grant[] }>(`/api/agents/${agentId}/tool_grants`),
      ]);
      setAvailableTools(catalog.items ?? []);
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
  }, [agentId, workspaceId]);

  const grantedNames = new Set(activeGrants.map((g) => g.tool_name));
  const installedNames = new Set(availableTools.map((t) => t.name));

  // Ungranted tools that are installed in the environment.
  const ungrantedTools = availableTools.filter((t) => !grantedNames.has(t.name));

  // Grants whose tool is NOT in the installed catalog (unbacked).
  const unbackedGrants = activeGrants.filter(
    (g) => workspaceId && !installedNames.has(g.tool_name),
  );

  const handleGrant = async () => {
    if (!selectedTool || grantReason.trim().length < 3) return;
    setGrantLoading(true);
    try {
      await apiRequest(`/api/agents/${agentId}/tool_grants`, {
        method: "POST",
        body: JSON.stringify({
          tool_name: selectedTool,
          changelog: grantReason,
          workspace_id: workspaceId,
        }),
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
      <h3>Tool Authorization</h3>
      <p className="muted">
        Authorize which tools this agent may call at runtime. This is the{" "}
        <strong>single</strong> authorization surface — workspace provisioning
        (MCP servers, host capabilities) controls <em>availability</em>, not
        permission.
      </p>
      {workspaceId && (
        <p className="muted" style={{ fontSize: 11 }}>
          Available tools sourced from the <em>installed</em> catalog of
          workspace <code>{workspaceId}</code>.
        </p>
      )}
      {error && <div className="error">{error}</div>}

      {/* Unbacked grant warnings */}
      {unbackedGrants.length > 0 && (
        <section style={{ marginBottom: 12 }}>
          <h4 style={{ color: "orange" }}>
            ⚠ Unbacked Grants ({unbackedGrants.length})
          </h4>
          <div className="dim" style={{ fontSize: 11, marginBottom: 6 }}>
            These tools are granted but not currently installed in the
            workspace. They will have no effect until provisioning catches up.
          </div>
          {unbackedGrants.map((g) => (
            <div key={g.tool_name} className="grant-row" style={{ opacity: 0.7 }}>
              <span className="tool-name">{g.tool_name}</span>
              <span className="grant-meta" style={{ color: "orange" }}>
                not available in this environment
              </span>
              <input
                type="text"
                placeholder="Reason to revoke (required)"
                value={revokeReason[g.tool_name] ?? ""}
                onChange={(e) =>
                  setRevokeReason((prev) => ({
                    ...prev,
                    [g.tool_name]: e.target.value,
                  }))
                }
              />
              <button
                onClick={() => handleRevoke(g.tool_name)}
                disabled={
                  (revokeReason[g.tool_name]?.trim().length ?? 0) < 3
                }
              >
                Revoke
              </button>
            </div>
          ))}
        </section>
      )}

      {/* Active (backed) grants */}
      <section>
        <h4>Active Grants ({activeGrants.length})</h4>
        {activeGrants.length === 0 && <p className="muted">No tools granted.</p>}
        {activeGrants
          .filter((g) => !unbackedGrants.includes(g))
          .map((grant) => (
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
                {t.name}{" "}
                {t.kind && `(${t.kind === "host_env" ? "host_env" : t.kind})`}
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
          {workspaceId
            ? "No tools or resources are installed in this workspace."
            : "No shared tools are registered. Consumer apps register tools via the agentbox.agent_tools entry-point group."}
        </p>
      )}
    </div>
  );
}
