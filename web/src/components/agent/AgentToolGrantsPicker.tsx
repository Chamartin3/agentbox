import { useState, useEffect, useMemo } from "react";
import { apiRequest } from "../../api/http";
import { type RunnerBackend } from "../../api/client";

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
  workspaceId: string | null | undefined;
  /** The agent's *saved* workspace. When it differs from workspaceId the user
   * is previewing a not-yet-saved workspace change; granted tools missing from
   * the previewed catalog are the ones a save would prune. */
  savedWorkspaceId?: string | null;
  /** Backend id of the agent's bound runner profile. When the descriptor for
   * this id has supports_mcp=false, the picker hides MCP / host_env tools and
   * restricts the catalog to native_tools only. */
  harnessBackendId?: string | null;
  /** Bumped by the parent after a save so the picker re-fetches grants (a
   * workspace-change prune revokes them server-side). */
  reloadToken?: number;
}

// Collapse the raw canonical namespaces into a few intuitive buckets.
const CATEGORY: Record<string, string> = {
  fs: "files",
  shell: "system",
  env: "system",
  agentbox: "system",
  agent: "system",
  http: "web",
  web: "web",
  git: "git",
  todo: "tasks",
};

function category(name: string): string {
  const dot = name.indexOf(".");
  const ns = dot > 0 ? name.slice(0, dot) : "other";
  return CATEGORY[ns] ?? "other";
}

// Source group for an item: MCP callables get their own per-server group
// ("mcp: <server>") so it's obvious which tools come from a linked MCP server;
// everything else falls back to the namespace bucket.
function categoryOf(t: CatalogItem): string {
  return t.server ? `mcp: ${t.server}` : category(t.name);
}

function shortName(name: string): string {
  const dot = name.indexOf(".");
  return dot > 0 ? name.slice(dot + 1) : name;
}

export function AgentToolGrantsPicker({ agentId, workspaceId, savedWorkspaceId, harnessBackendId, reloadToken }: Props) {
  const [availableTools, setAvailableTools] = useState<CatalogItem[]>([]);
  const [activeGrants, setActiveGrants] = useState<Grant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Local selection = desired granted set. Diffed against activeGrants on apply.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState("");
  const [applying, setApplying] = useState(false);

  // Filters
  const [query, setQuery] = useState("");
  const [catFilter, setCatFilter] = useState<string>("all");

  // Browse-all: union with the global catalog
  const [showAll, setShowAll] = useState(false);
  const [allTools, setAllTools] = useState<CatalogItem[]>([]);
  const [allToolsLoaded, setAllToolsLoaded] = useState(false);

  // Backend descriptor for MCP-capability filtering
  const [harnessDescriptor, setHarnessDescriptor] = useState<RunnerBackend | null>(null);

  // Enabled MCP servers associated with the workspace — including any that
  // haven't been discovered yet (0 tools). Drives the source tabs so a
  // linked server is visible even before discovery has run.
  const [mcpServers, setMcpServers] = useState<string[]>([]);
  const [refreshingMcp, setRefreshingMcp] = useState(false);

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
      setSelected(new Set((grants.items ?? []).map((g) => g.tool_name)));
      if (workspaceId) {
        try {
          const mcp = await apiRequest<{ servers: { name: string; enabled: boolean }[] }>(
            `/api/workspaces/${workspaceId}/mcp/servers`,
          );
          setMcpServers((mcp.servers ?? []).filter((s) => s.enabled).map((s) => s.name));
        } catch {
          setMcpServers([]);
        }
      } else {
        setMcpServers([]);
      }
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const refreshDiscovery = async () => {
    if (!workspaceId) return;
    setRefreshingMcp(true);
    try {
      await apiRequest(`/api/workspaces/${workspaceId}/mcp/refresh`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshingMcp(false);
    }
  };

  useEffect(() => { void refresh(); }, [agentId, workspaceId, reloadToken]);

  // Fetch the backend descriptor for the harness so we can check supports_mcp.
  useEffect(() => {
    if (!harnessBackendId) {
      setHarnessDescriptor(null);
      return;
    }
    apiRequest<RunnerBackend[]>("/api/runner-backends")
      .then((backends) => {
        const match = backends.find((b) => b.id === harnessBackendId) ?? null;
        setHarnessDescriptor(match);
      })
      .catch(() => setHarnessDescriptor(null));
  }, [harnessBackendId]);

  // When the harness cannot invoke MCP, restrict to native_tools only.
  const nativeOnlyMode = harnessDescriptor !== null && harnessDescriptor.supports_mcp === false;
  const nativeToolSet = useMemo(
    () => (nativeOnlyMode ? new Set(harnessDescriptor?.native_tools ?? []) : null),
    [nativeOnlyMode, harnessDescriptor],
  );

  const toggleBrowseAll = async () => {
    if (!showAll && !allToolsLoaded) {
      try {
        const catalog = await apiRequest<{ items: CatalogItem[] }>("/api/agent_tools");
        setAllTools(catalog.items ?? []);
        setAllToolsLoaded(true);
      } catch (e) {
        setError(String(e));
        return;
      }
    }
    setShowAll((v) => !v);
  };

  const grantedNames = useMemo(() => new Set(activeGrants.map((g) => g.tool_name)), [activeGrants]);
  const installedNames = useMemo(() => new Set(availableTools.map((t) => t.name)), [availableTools]);

  // Only when previewing a not-yet-saved workspace change: the granted tools
  // missing from the previewed catalog are exactly what a save would prune.
  const pendingPrune = useMemo(() => {
    if ((workspaceId ?? null) === (savedWorkspaceId ?? null)) return [];
    return [...grantedNames].filter((n) => !installedNames.has(n));
  }, [workspaceId, savedWorkspaceId, grantedNames, installedNames]);

  const fullCatalog: CatalogItem[] = useMemo(() => {
    const base = showAll
      ? [...availableTools, ...allTools.filter((t) => !installedNames.has(t.name))]
      : [...availableTools];
    for (const g of activeGrants) {
      if (!base.some((t) => t.name === g.tool_name)) {
        const isOverGrant = nativeOnlyMode && !nativeToolSet?.has(g.tool_name);
        base.push({
          name: g.tool_name,
          description: isOverGrant
            ? "not available on this harness — MCP / host-env tools cannot run with this backend"
            : "granted — not installed in this workspace",
          kind: "unbacked",
        });
      }
    }

    if (nativeOnlyMode && nativeToolSet) {
      // Keep items whose canonical name is in the native set. MCP-server and
      // host_env items are never in native_tools so they drop automatically.
      // Over-granted items (kind=unbacked, not in native set) are kept so the
      // user can see and revoke them — they render with the disabled style.
      return base.filter(
        (t) => nativeToolSet.has(t.name) || (t.kind === "unbacked" && !nativeToolSet.has(t.name)),
      );
    }

    return base;
  }, [showAll, availableTools, allTools, installedNames, activeGrants, nativeOnlyMode, nativeToolSet]);

  const categories = useMemo(() => {
    const set = new Set(fullCatalog.map((t) => categoryOf(t)));
    // Surface every enabled workspace MCP server as a source, even if it has
    // no discovered tools yet — otherwise a linked-but-undiscovered server is
    // invisible here.
    for (const s of mcpServers) set.add(`mcp: ${s}`);
    return [...set].sort((a, b) => (a === "other" ? 1 : b === "other" ? -1 : a.localeCompare(b)));
  }, [fullCatalog, mcpServers]);

  // When an "mcp: <server>" tab is selected, the server name (for the
  // discovery affordance shown when it has no tools yet).
  const activeMcpServer = catFilter.startsWith("mcp: ") ? catFilter.slice(5) : null;

  const matchesText = (t: CatalogItem) => {
    const q = query.trim().toLowerCase();
    return !q || t.name.toLowerCase().includes(q) || (t.description ?? "").toLowerCase().includes(q);
  };

  // Enabled = currently selected (respects text filter, ignores category tab
  // so you never lose sight of what's on). Available = the rest (both filters).
  const enabledList = useMemo(
    () => fullCatalog.filter((t) => selected.has(t.name) && matchesText(t)).sort((a, b) => a.name.localeCompare(b.name)),
    [fullCatalog, selected, query],
  );
  const availableList = useMemo(
    () =>
      fullCatalog
        .filter((t) => !selected.has(t.name) && matchesText(t))
        .filter((t) => catFilter === "all" || categoryOf(t) === catFilter)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [fullCatalog, selected, query, catFilter],
  );

  const toggle = (name: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const selectAllAvailable = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      for (const t of availableList) if (installedNames.has(t.name)) next.add(t.name);
      return next;
    });
  const clearAllEnabled = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      for (const t of enabledList) next.delete(t.name);
      return next;
    });

  const toGrant = [...selected].filter((n) => !grantedNames.has(n));
  const toRevoke = [...grantedNames].filter((n) => !selected.has(n));
  const dirty = toGrant.length + toRevoke.length;

  const apply = async () => {
    if (reason.trim().length < 3 || !dirty) return;
    setApplying(true);
    try {
      for (const name of toGrant) {
        await apiRequest(`/api/agents/${agentId}/tool_grants`, {
          method: "POST",
          body: JSON.stringify({ tool_name: name, changelog: reason, workspace_id: workspaceId }),
        });
      }
      for (const name of toRevoke) {
        await apiRequest(`/api/agents/${agentId}/tool_grants/${name}`, {
          method: "DELETE",
          body: JSON.stringify({ changelog: reason }),
        });
      }
      setReason("");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setApplying(false);
    }
  };

  const resetSelection = () => setSelected(new Set(grantedNames));

  const renderBox = (t: CatalogItem) => {
    const isInstalled = installedNames.has(t.name);
    const isGranted = grantedNames.has(t.name);
    const isSelected = selected.has(t.name);
    // Disable if not accessible in the workspace, OR if the harness cannot run it.
    const unavailableOnHarness = nativeOnlyMode && nativeToolSet !== null && !nativeToolSet.has(t.name);
    const disabled = (!isInstalled && !isGranted) || unavailableOnHarness;
    const changed = isSelected !== isGranted;
    return (
      <label
        key={t.name}
        className={[
          "tool-box",
          isSelected ? "tool-box--on" : "tool-box--off",
          disabled ? "tool-box--disabled" : "",
          changed ? "tool-box--changed" : "",
        ].filter(Boolean).join(" ")}
        title={t.description || (disabled ? `not installed in workspace ${workspaceId}` : undefined)}
      >
        <div className="tool-box-main">
          <input type="checkbox" checked={isSelected} disabled={disabled} onChange={() => toggle(t.name)} />
          <span className="tool-box-name">{shortName(t.name)}</span>
        </div>
        <span className="tool-box-group">{categoryOf(t)}</span>
      </label>
    );
  };

  if (loading) return <div className="tools-panel"><div style={{ padding: "12px 0" }}>Loading tools…</div></div>;

  return (
    <div className="tools-panel">
      <div className="tools-panel-header">
        <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
          <h3 style={{ margin: 0 }}>Tools</h3>
          <span className="tools-count">{grantedNames.size} enabled</span>
          <span className="tools-total dim">of <strong>{installedNames.size}</strong> available</span>
        </div>
        <button onClick={() => void toggleBrowseAll()} style={{ fontSize: 11, padding: "2px 8px" }}>
          {showAll ? "hide global catalog" : "browse all"}
        </button>
      </div>

      {workspaceId && showAll && (
        <p className="dim tools-source">Global-catalog tools not installed in this workspace are shown disabled.</p>
      )}
      {nativeOnlyMode && (
        <p className="dim tools-source" style={{ color: "var(--warning, #b8860b)" }}>
          {harnessDescriptor?.id ?? "This harness"} runs native tools only — MCP servers and host-env tools are not available for this harness.
        </p>
      )}
      {pendingPrune.length > 0 && (
        <p className="tools-source" style={{ color: "var(--yellow)" }}>
          {pendingPrune.length} assigned tool{pendingPrune.length === 1 ? "" : "s"} not available in{" "}
          <strong>{workspaceId || "the default (dedicated) workspace"}</strong> —{" "}
          {pendingPrune.length === 1 ? "it" : "they"} will be removed when you save.
        </p>
      )}
      {error && <div className="tools-error">{error}</div>}

      {/* Search + source filter, side by side. The source tabs live here (not
          buried in the Available subhead) so filtering by source is a
          top-level control. */}
      <div className="tools-controls">
        <input
          className="tools-filter"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter tools…"
        />
        <div className="tools-type-tabs">
          <button className={`tools-type-tab${catFilter === "all" ? " active" : ""}`} onClick={() => setCatFilter("all")}>all</button>
          {categories.map((c) => (
            <button key={c} className={`tools-type-tab${catFilter === c ? " active" : ""}`} onClick={() => setCatFilter(c)}>{c}</button>
          ))}
        </div>
      </div>

      {/* Enabled — the agent's current toolset, shown apart from the catalog */}
      <div className="tools-subhead">
        <span className="tools-subhead-title">Enabled</span>
        <span className="tools-subhead-count">{enabledList.length}</span>
        {enabledList.length > 0 && (
          <button className="tools-linkbtn" onClick={clearAllEnabled}>clear all</button>
        )}
      </div>
      {enabledList.length === 0 ? (
        <p className="dim tools-empty">No tools enabled yet — pick from the catalog below.</p>
      ) : (
        <div className="tools-grid tools-grid--enabled">{enabledList.map(renderBox)}</div>
      )}

      {/* Available — the rest of the catalog, grouped by category tabs */}
      <div className="tools-subhead">
        <span className="tools-subhead-title">Available</span>
        <span className="tools-subhead-count">{availableList.length}</span>
        {catFilter !== "all" && (
          <button className="tools-linkbtn" onClick={() => setCatFilter("all")}>
            {catFilter} ✕
          </button>
        )}
        {availableList.some((t) => installedNames.has(t.name)) && (
          <button className="tools-linkbtn" onClick={selectAllAvailable}>select all</button>
        )}
      </div>
      {availableList.length === 0 ? (
        activeMcpServer ? (
          <p className="dim tools-empty">
            No tools discovered for <strong>{activeMcpServer}</strong> yet.{" "}
            <button className="tools-linkbtn" onClick={() => void refreshDiscovery()} disabled={refreshingMcp}>
              {refreshingMcp ? "discovering…" : "run discovery"}
            </button>
          </p>
        ) : (
          <p className="dim tools-empty">
            {fullCatalog.length === 0
              ? workspaceId ? "No tools installed in this workspace." : "No shared tools registered."
              : "Everything here is already enabled or filtered out."}
          </p>
        )
      ) : (
        <div className="tools-grid">{availableList.map(renderBox)}</div>
      )}

      {/* Apply bar — only when there are pending changes */}
      {dirty > 0 && (
        <div className="tools-apply-bar">
          <span className="tools-apply-summary">
            {toGrant.length > 0 && <span className="tools-diff-grant">+{toGrant.length}</span>}
            {toRevoke.length > 0 && <span className="tools-diff-revoke">−{toRevoke.length}</span>}
            <span className="dim" style={{ marginLeft: 6 }}>pending</span>
          </span>
          <input
            className="tools-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && reason.trim().length >= 3) void apply(); }}
            placeholder="reason (required, min 3 chars)"
          />
          <button className="primary" disabled={reason.trim().length < 3 || applying} onClick={() => void apply()}>
            {applying ? "applying…" : `apply ${dirty} change${dirty === 1 ? "" : "s"}`}
          </button>
          <button onClick={resetSelection} disabled={applying}>reset</button>
        </div>
      )}
    </div>
  );
}
