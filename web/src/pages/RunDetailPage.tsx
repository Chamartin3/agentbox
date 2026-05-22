import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AgentDef, GuardrailRow, PromptFragment, RunPromptDoc, RunRecord, UsageRecord, api } from '../api/client';
import EventStream from '../components/EventStream';
import ConversationView from '../components/ConversationView';
import RunCommentThread from '../components/RunCommentThread';
import { fmtCost, fmtDt, fmtMs, fmtNum, fmtRelative } from '../util/format';

function durationMs(r: RunRecord): number | null {
  if (!r.finished_at) return null;
  return new Date(r.finished_at).getTime() - new Date(r.created_at).getTime();
}

interface StreamEvent {
  type: string;
  [k: string]: unknown;
}

// ────────────────────────────────────────────────────────────── error parsing

function parseError(err: string | null): { headline: string; detail: string | null } {
  if (!err) return { headline: '', detail: null };
  const trimmed = err.trim();
  const httpMatch = trimmed.match(/^HTTP (\d+): (.*)$/s);
  if (httpMatch) {
    const [, status, body] = httpMatch;
    const innerErr = tryJson(body)?.error;
    if (typeof innerErr === 'string') {
      const upstream = tryUnwrapUpstream(innerErr);
      return { headline: `HTTP ${status} from upstream`, detail: upstream ?? innerErr };
    }
    return { headline: `HTTP ${status}`, detail: body };
  }
  const colon = trimmed.indexOf(':');
  if (colon > 0 && colon < 80) {
    return { headline: trimmed.slice(0, colon), detail: trimmed.slice(colon + 1).trim() };
  }
  return { headline: 'Error', detail: trimmed };
}
function tryJson(s: string): Record<string, unknown> | null {
  try { return JSON.parse(s) as Record<string, unknown>; } catch { return null; }
}
function tryUnwrapUpstream(s: string): string | null {
  const msgMatch = s.match(/'message':\s*'([^']+)'|"message":\s*"([^"]+)"/);
  const modelMatch = s.match(/model_name:\s*([^\s,]+)/);
  const statusMatch = s.match(/status_code:\s*(\d+)/);
  if (msgMatch) {
    const msg = msgMatch[1] ?? msgMatch[2];
    const bits: string[] = [msg];
    if (modelMatch) bits.push(`model=${modelMatch[1]}`);
    if (statusMatch) bits.push(`status=${statusMatch[1]}`);
    return bits.join(' · ');
  }
  return null;
}

function prettyText(s: string): { text: string; isJson: boolean } {
  const t = s.trim();
  if (!t) return { text: '', isJson: false };
  if (t.startsWith('{') || t.startsWith('[')) {
    try { return { text: JSON.stringify(JSON.parse(t), null, 2), isJson: true }; } catch { /* */ }
  }
  return { text: s, isJson: false };
}

// ──────────────────────────────────────────────────────────────── components

function StatusPill({ status }: { status: string }) {
  let cls: string;
  if (status === 'ok') cls = 'ok';
  else if (status === 'running') cls = 'running';
  else if (status === 'timeout' || status === 'stopped' || status === 'incomplete')
    cls = 'eph';
  else if (status === 'failed') cls = 'failed';
  else cls = 'error';
  return <span className={`pill ${cls}`}>{status}</span>;
}

function Tag({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: 'default' | 'mono' | 'accent';
}) {
  return (
    <span className={`meta-tag ${tone ?? 'default'}`}>
      <span className="meta-tag-label">{label}</span>
      <span className="meta-tag-value">{value}</span>
    </span>
  );
}

function CodeBlock({ value, language }: { value: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="code-block">
      <div className="code-block-bar">
        <span className="dim" style={{ fontSize: 11 }}>
          {language ?? 'text'} · {value.length.toLocaleString()} chars
        </span>
        <button onClick={copy} style={{ fontSize: 11, padding: '2px 8px' }}>
          {copied ? 'copied!' : 'copy'}
        </button>
      </div>
      <pre style={{ margin: 0 }}>{value}</pre>
    </div>
  );
}

interface ToolCallRow {
  index: number;
  tool: string;
  arguments: unknown;
  ts: string | undefined;
  resultTs: string | undefined;
  ok: boolean | undefined;
  excerpt: string | undefined;
}

function pairToolCalls(events: StreamEvent[]): ToolCallRow[] {
  const pending: Record<string, number> = {};
  const rows: ToolCallRow[] = [];
  const unkeyedStack: number[] = [];
  for (const ev of events) {
    const t = String(ev.type || '');
    if (t === 'tool_call') {
      const idx = rows.length;
      rows.push({
        index: idx,
        tool: String(ev.tool ?? ''),
        arguments: ev.arguments,
        ts: typeof ev.ts === 'string' ? ev.ts : undefined,
        resultTs: undefined,
        ok: undefined,
        excerpt: undefined,
      });
      const cid = typeof ev.call_id === 'string' ? ev.call_id : null;
      if (cid) pending[cid] = idx;
      else unkeyedStack.push(idx);
    } else if (t === 'tool_result') {
      const cid = typeof ev.call_id === 'string' ? ev.call_id : null;
      let idx: number | undefined;
      if (cid && cid in pending) {
        idx = pending[cid];
        delete pending[cid];
      } else {
        // Fallback: pair with the most recent unmatched call of the same tool.
        for (let i = unkeyedStack.length - 1; i >= 0; i -= 1) {
          const c = rows[unkeyedStack[i]];
          if (c.tool === String(ev.tool ?? '') && c.ok === undefined) {
            idx = unkeyedStack[i];
            unkeyedStack.splice(i, 1);
            break;
          }
        }
      }
      if (idx === undefined) {
        // Result without a matching call — surface as its own row.
        rows.push({
          index: rows.length,
          tool: String(ev.tool ?? ''),
          arguments: undefined,
          ts: undefined,
          resultTs: typeof ev.ts === 'string' ? ev.ts : undefined,
          ok: typeof ev.ok === 'boolean' ? ev.ok : undefined,
          excerpt: typeof ev.result_excerpt === 'string' ? ev.result_excerpt : undefined,
        });
      } else {
        const row = rows[idx];
        row.resultTs = typeof ev.ts === 'string' ? ev.ts : row.resultTs;
        row.ok = typeof ev.ok === 'boolean' ? ev.ok : row.ok;
        row.excerpt =
          typeof ev.result_excerpt === 'string' ? ev.result_excerpt : row.excerpt;
      }
    }
  }
  return rows;
}

function ToolCallsSection({ events }: { events: StreamEvent[] }) {
  const rows = useMemo(() => pairToolCalls(events), [events]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows) c[r.tool] = (c[r.tool] ?? 0) + 1;
    return Object.entries(c).sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const [expanded, setExpanded] = useState<number | null>(null);

  if (rows.length === 0) {
    return (
      <section className="section">
        <h2 style={{ borderBottom: 'none' }}>Tool calls</h2>
        <p className="dim" style={{ margin: 0 }}>
          none captured (PreToolUse/PostToolUse hooks run on the next claude_code run)
        </p>
      </section>
    );
  }

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h2 style={{ border: 'none', margin: 0 }}>
          Tool calls <span className="dim">({rows.length})</span>
        </h2>
        <div className="dim" style={{ fontSize: 12 }}>
          {counts.slice(0, 6).map(([name, n]) => (
            <span key={name} style={{ marginLeft: 10 }}>
              <code>{name}</code>×{n}
            </span>
          ))}
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th style={{ width: 30 }}>#</th>
            <th>Tool</th>
            <th>Arguments</th>
            <th style={{ width: 70 }}>Result</th>
            <th style={{ width: 110 }}>Duration</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const argText =
              r.arguments === undefined
                ? '—'
                : typeof r.arguments === 'string'
                  ? r.arguments
                  : JSON.stringify(r.arguments);
            const argPreview = argText.length > 140 ? `${argText.slice(0, 140)}…` : argText;
            const dur =
              r.ts && r.resultTs
                ? new Date(r.resultTs).getTime() - new Date(r.ts).getTime()
                : null;
            const isOpen = expanded === r.index;
            return (
              <Fragment key={r.index}>
                <tr
                  onClick={() => setExpanded(isOpen ? null : r.index)}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="dim">{r.index + 1}</td>
                  <td><code>{r.tool || '—'}</code></td>
                  <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{argPreview}</td>
                  <td>
                    {r.ok === undefined ? (
                      <span className="dim">…</span>
                    ) : r.ok ? (
                      <span className="pill ok">ok</span>
                    ) : (
                      <span className="pill error">fail</span>
                    )}
                  </td>
                  <td className="dim">{dur === null ? '—' : fmtMs(dur)}</td>
                </tr>
                {isOpen && (
                  <tr>
                    <td colSpan={5} style={{ background: 'var(--bg-soft, #0d1117)' }}>
                      <div style={{ padding: 8, fontSize: 12 }}>
                        <div className="dim" style={{ marginBottom: 4 }}>arguments</div>
                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {argText}
                        </pre>
                        {r.excerpt !== undefined && (
                          <>
                            <div className="dim" style={{ margin: '8px 0 4px' }}>
                              result excerpt
                            </div>
                            <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                              {r.excerpt}
                            </pre>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}



// ──────────────────────────────────────────────────────── prompt fragments

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function FragmentRow({ f, total }: { f: PromptFragment; total: number }) {
  const pct = total > 0 ? Math.round((f.size_bytes / total) * 100) : 0;
  return (
    <details className="frag" style={{ borderBottom: '1px solid var(--border)' }}>
      <summary
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 10px',
          cursor: 'pointer',
        }}
      >
        <code style={{ fontWeight: 600 }}>{f.name}</code>
        <span className="tag" style={{ fontSize: 10 }}>{f.injected_by}</span>
        <span className="dim" style={{ fontSize: 11 }}>from {f.source}</span>
        {!f.inspectable && <span className="pill eph" style={{ fontSize: 10 }}>opaque</span>}
        <span style={{ flex: 1 }} />
        <span className="dim" style={{ fontSize: 11 }}>
          {fmtBytes(f.size_bytes)} · {pct}%
        </span>
      </summary>
      <div style={{ padding: 10 }}>
        <div
          style={{
            height: 4,
            background: 'var(--bg)',
            borderRadius: 2,
            overflow: 'hidden',
            marginBottom: 8,
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${pct}%`,
              background: f.inspectable ? 'var(--accent)' : 'var(--fg-muted)',
            }}
          />
        </div>
        <pre
          style={{
            margin: 0,
            padding: 10,
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            maxHeight: '40vh',
            overflow: 'auto',
            fontSize: 12,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {f.content}
        </pre>
      </div>
    </details>
  );
}

// ──────────────────────────────────────────────────────────────────── page

export default function RunDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rerunning, setRerunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [usage, setUsage] = useState<UsageRecord | null>(null);
  const [guards, setGuards] = useState<GuardrailRow[]>([]);
  const [agent, setAgent] = useState<AgentDef | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [promptDoc, setPromptDoc] = useState<RunPromptDoc | null>(null);
  const [isLive, setIsLive] = useState(false);
  const [eventView, setEventView] = useState<'conversation' | 'events'>('conversation');
  const [tab, setTab] = useState<'prompt' | 'conversation' | 'tools' | 'checks' | 'snapshot'>('prompt');
  const wsRef = useRef<WebSocket | null>(null);
  // Re-render every 30s so "5m ago" labels stay fresh.
  const [, setNow] = useState(Date.now());

  const loadMeta = async () => {
    try {
      const r = await api.getRun(id);
      setRun(r.run);
      setUsage(r.usage);
      setGuards(r.guardrails);
      // Fetch agent metadata for context tags.
      api.listAgents()
        .then((list) => setAgent(list.find((a) => a.id === r.run.agent_id) ?? null))
        .catch(() => {});
      api.getRunPrompt(id).then(setPromptDoc).catch(() => {});
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadMeta();
    // Always load the transcript on mount so we have events even before
    // the WebSocket connects (or if the run is already finished).
    setEventsLoading(true);
    setEventsError(null);
    // Key events by (ts + type + index-of-kind) so merging a freshly
    // re-fetched transcript with live WS events doesn't drop or
    // duplicate anything that arrived in between.
    const eventKey = (ev: StreamEvent, fallbackIdx: number): string => {
      const ts = String(ev.ts ?? '');
      const type = String(ev.type ?? '');
      const text = String(ev.text ?? ev.message ?? '');
      return `${ts}|${type}|${text.slice(0, 64)}|${fallbackIdx}`;
    };
    const mergeEvents = (existing: StreamEvent[], incoming: StreamEvent[]): StreamEvent[] => {
      const seen = new Set<string>();
      existing.forEach((ev, i) => seen.add(eventKey(ev, i)));
      const out = [...existing];
      incoming.forEach((ev, i) => {
        const k = eventKey(ev, i);
        if (!seen.has(k)) {
          seen.add(k);
          out.push(ev);
        }
      });
      return out;
    };
    api.getTranscript(id)
      .then((evs) => {
        setEvents((curr) => mergeEvents(curr, evs as StreamEvent[]));
        setEventsLoading(false);
      })
      .catch(() => { setEventsError('failed to load transcript'); setEventsLoading(false); });
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/api/runs/${id}/stream`);
    wsRef.current = ws;
    ws.onopen = () => { setIsLive(true); setEventsError(null); };
    ws.onmessage = (m) => {
      const ev = JSON.parse(m.data) as StreamEvent;
      setEvents((curr) => mergeEvents(curr, [ev]));
    };
    ws.onclose = () => {
      setIsLive(false);
      loadMeta();
      // Refresh transcript after WS close in case new events
      // arrived between the initial load and the WS disconnect.
      // Merge (not replace) so any live events still in state survive.
      setTimeout(() => {
        api.getTranscript(id)
          .then((evs) => setEvents((curr) => mergeEvents(curr, evs as StreamEvent[])))
          .catch(() => {});
      }, 100);
    };
    return () => { ws.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Tick for relative-time labels.
  useEffect(() => {
    const h = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(h);
  }, []);

  const err = useMemo(() => parseError(run?.error ?? null), [run?.error]);
  const inputPretty = useMemo(() => prettyText(run?.input ?? ''), [run?.input]);
  const outputPretty = useMemo(() => prettyText(run?.output ?? ''), [run?.output]);
  const duration = run ? durationMs(run) : null;
  const tokens = (usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0);
  const toolCallCount = useMemo(
    () => events.filter((e) => e.type === 'tool_call').length,
    [events],
  );

  if (!run) return <p className="dim">loading…</p>;

  // `rendered_prompt` may arrive as either an object or a JSON-encoded string
  // (the DB stores it as text and the API doesn't re-parse). Normalize.
  const renderedPrompt: { system: string; user: string; schema: unknown } | null = (() => {
    const rp = run.rendered_prompt as unknown;
    if (!rp) return null;
    let obj: Record<string, unknown> | null = null;
    if (typeof rp === 'string') {
      try {
        const parsed = JSON.parse(rp);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          obj = parsed as Record<string, unknown>;
        }
      } catch { /* fall through */ }
    } else if (typeof rp === 'object' && !Array.isArray(rp)) {
      obj = rp as Record<string, unknown>;
    }
    if (!obj) return null;
    return {
      system: typeof obj.system === 'string' ? obj.system : '',
      user: typeof obj.user === 'string' ? obj.user : '',
      schema: obj.schema,
    };
  })();

  // Variables can come back as either an object or a JSON-encoded string.
  // Normalize to a plain record so we can render it as a KV table without
  // iterating string characters.
  const variablesObj: Record<string, unknown> | null = (() => {
    const v = run.variables;
    if (!v) return null;
    if (typeof v === 'string') {
      try {
        const parsed = JSON.parse(v);
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
          ? (parsed as Record<string, unknown>)
          : null;
      } catch {
        return null;
      }
    }
    if (typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
    return null;
  })();
  const variablesJson = variablesObj ? JSON.stringify(variablesObj, null, 2) : null;
  const inputIsSameAsVariables =
    !!variablesJson && inputPretty.isJson && inputPretty.text === variablesJson;
  const variablesEntries = variablesObj ? Object.entries(variablesObj) : [];

  const workspace = agent?.workspace ?? null;
  const isEphemeral = workspace === '<ephemeral>';
  // runner_snapshot is the historical truth of what executed this run.
  // Prefer it over agent.runner (current config) and over the bound
  // profile (mutable, can be edited/rebound after the run).
  const runnerSnapshot = (run as any)?.runner_snapshot ?? null;
  const snapshotMissing =
    runnerSnapshot && (runnerSnapshot.snapshot === 'missing' || runnerSnapshot.snapshot === 'invalid');
  const runnerKind = run.backend
    || (runnerSnapshot && !snapshotMissing && runnerSnapshot.backend)
    || agent?.runner?.kind
    || null;
  const modelName = run.configured_model
    || (runnerSnapshot && !snapshotMissing && runnerSnapshot.model)
    || usage?.model
    || agent?.model
    || null;
  const runnerProfileName = (runnerSnapshot && !snapshotMissing && runnerSnapshot.profile_name) || null;
  const cacheTokens = (usage?.cache_read_tokens ?? 0) + (usage?.cache_write_tokens ?? 0);

  return (
    <div className="stack">
      {/* ── Compact header ───────────────────────────────────────────── */}
      <div className="run-header-compact">
        <div>
          <div className="crumb">
            <Link to="/" className="dim">runs</Link>
            <span style={{ margin: '0 6px' }}>/</span>
            <code style={{ fontSize: 11 }}>{id.slice(0, 12)}…</code>
          </div>
          <h1>
            <Link to={`/agents/${run.agent_id}`}>{run.agent_id}</Link>
            {run.agent_version != null && (
              <Link
                to={`/agents/${run.agent_id}/versions`}
                style={{ marginLeft: 8, fontSize: 13, color: 'var(--fg-muted)' }}
                title="View agent versions"
              >
                @v{run.agent_version}
              </Link>
            )}
          </h1>
        </div>
        <StatusPill status={run.status} />
        {runnerKind && <span className="stat">runner<strong>{runnerKind}</strong></span>}
        {runnerProfileName && <span className="stat">profile<strong>{runnerProfileName}</strong></span>}
        {modelName && <span className="stat">model<strong>{modelName}</strong></span>}
        <span className="spacer" />
        {run.status === 'running' && (
          <button
            disabled={cancelling}
            onClick={async () => {
              if (!confirm('Cancel this run? The agent will be stopped and marked incomplete.')) return;
              setCancelling(true);
              try {
                await api.cancelRun(id);
                const r = await api.getRun(id);
                setRun(r.run);
              } catch (e) {
                console.error(e);
                alert('cancel failed');
              } finally {
                setCancelling(false);
              }
            }}
            title="Stop this run and mark it incomplete"
            style={{ marginRight: 8 }}
          >
            {cancelling ? 'Stopping…' : '■ Stop'}
          </button>
        )}
        <button
          disabled={rerunning}
          onClick={async () => {
            setRerunning(true);
            try {
              const { run_id } = await api.rerunRun(id);
              navigate(`/runs/${run_id}`);
            } catch (e) {
              console.error(e);
              alert('rerun failed');
            } finally {
              setRerunning(false);
            }
          }}
          title="Re-execute this agent with the same input"
        >
          {rerunning ? 'Rerunning…' : '↻ Rerun'}
        </button>
      </div>

      {/* ── Meta strip + plumbing (folded) ──────────────────────────── */}
      <div className="meta-tags">
        <Tag label="started" value={fmtRelative(run.created_at)} tone="accent" />
        {run.finished_at && <Tag label="finished" value={fmtRelative(run.finished_at)} />}
        {agent?.session_mode && <Tag label="session" value={agent.session_mode} />}
        {workspace && (
          isEphemeral ? (
            <Tag label="workspace" value="ephemeral" />
          ) : (
            <span className="meta-tag mono">
              <span className="meta-tag-label">workspace</span>
              <span className="meta-tag-value">
                <Link to={`/workspaces/${workspace}`}>{workspace}</Link>
              </span>
            </span>
          )
        )}
        {run.session_id && <Tag label="session_id" value={run.session_id.slice(0, 8)} tone="mono" />}
        {agent?.description && (
          <span className="meta-tag">
            <span className="meta-tag-label">about</span>
            <span className="meta-tag-value" style={{ fontWeight: 400 }}>{agent.description}</span>
          </span>
        )}
      </div>

      {/* ── Stats row: runtime, tokens, cache, cost, events, tools ─── */}
      <div className="run-stats-row">
        <div className="stat-block">
          <span className="label">Runtime</span>
          <span className="value">{fmtMs(duration)}</span>
          <span className="sub" title={run.created_at}>
            {run.finished_at ? `${fmtRelative(run.created_at)} → ${fmtRelative(run.finished_at)}` : `started ${fmtRelative(run.created_at)}`}
          </span>
        </div>
        <div className="stat-block">
          <span className="label">Tokens</span>
          <span className="value">{fmtNum(tokens)}</span>
          <span className="sub">in {fmtNum(usage?.input_tokens)} · out {fmtNum(usage?.output_tokens)}</span>
        </div>
        <div className="stat-block">
          <span className="label">Cache</span>
          <span className="value">{fmtNum(cacheTokens)}</span>
          <span className="sub">read {fmtNum(usage?.cache_read_tokens)} · write {fmtNum(usage?.cache_write_tokens)}</span>
        </div>
        <div className="stat-block">
          <span className="label">Cost</span>
          <span className="value">{fmtCost(usage?.cost_usd)}</span>
          <span className="sub">{usage?.model ?? '—'}</span>
        </div>
        <div className="stat-block">
          <span className="label">Events</span>
          <span className="value">{fmtNum(events.length)}</span>
          <span className="sub">{toolCallCount} tool calls</span>
        </div>
        <div className="stat-block">
          <span className="label">Checks</span>
          <span className="value">
            {run.validation_status ? (
              <span className={`pill ${run.validation_status === 'ok' ? 'ok' : run.validation_status === 'warn' ? 'running' : 'error'}`}>
                {run.validation_status}
              </span>
            ) : '—'}
          </span>
          <span className="sub">{guards.length} guardrails</span>
        </div>
      </div>

      <details className="section" style={{ padding: '8px 14px' }}>
        <summary className="dim" style={{ cursor: 'pointer', fontSize: 12 }}>
          Plumbing — run id, workdir, transcript, timestamps
        </summary>
        <dl className="dl" style={{ marginTop: 10 }}>
          <dt>Run id</dt><dd><code>{run.id}</code></dd>
          <dt>Agent version</dt>
          <dd>
            {run.agent_version != null ? (
              <Link to={`/agents/${run.agent_id}/versions`}><code>v{run.agent_version}</code></Link>
            ) : <span className="dim">—</span>}
            {run.agent_version_id != null && <span className="dim" style={{ marginLeft: 8 }}>(id {run.agent_version_id})</span>}
          </dd>
          <dt>Session</dt><dd>{run.session_id ?? <span className="dim">—</span>}</dd>
          <dt>Workdir</dt><dd><code style={{ fontSize: 11 }}>{run.workdir ?? '—'}</code></dd>
          <dt>Transcript</dt><dd><code style={{ fontSize: 11 }}>{run.transcript_path ?? '—'}</code></dd>
          <dt>Config digest</dt><dd>{run.config_digest ? <code style={{ fontSize: 11 }}>{run.config_digest}</code> : <span className="dim">—</span>}</dd>
          <dt>Started</dt><dd>{fmtDt(run.created_at)} <span className="dim">({fmtRelative(run.created_at)})</span></dd>
          <dt>Finished</dt><dd>{fmtDt(run.finished_at)} {run.finished_at && <span className="dim">({fmtRelative(run.finished_at)})</span>}</dd>
        </dl>
      </details>

      {/* ── Error card (when present) ───────────────────────────────── */}
      {run.error && (
        <details className="section error-card" open style={{ padding: 0 }}>
          <summary className="error-card-summary">
            <span style={{ color: 'var(--red)', fontWeight: 500 }}>{err.headline || 'Run failed'}</span>
            {err.detail && <span className="dim" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginLeft: 8 }}>{err.detail}</span>}
          </summary>
          <div style={{ padding: '0 16px 12px' }}>
            {err.detail && (
              <p style={{ margin: '8px 0', whiteSpace: 'pre-wrap', fontSize: 13 }}>{err.detail}</p>
            )}
            <details>
              <summary className="dim" style={{ cursor: 'pointer', fontSize: 12 }}>raw error</summary>
              <pre style={{ marginTop: 8 }}>{run.error}</pre>
            </details>
          </div>
        </details>
      )}

      {/* ── Tab bar (sits high — first viewport) ────────────────────── */}
      <div className="run-tabs">
        <button className={tab === 'prompt' ? 'active' : ''} onClick={() => setTab('prompt')}>
          Prompt & I/O
        </button>
        <button className={tab === 'conversation' ? 'active' : ''} onClick={() => setTab('conversation')}>
          Conversation<span className="count">{events.length}</span>
        </button>
        <button className={tab === 'tools' ? 'active' : ''} onClick={() => setTab('tools')}>
          Tool calls<span className="count">{toolCallCount}</span>
        </button>
        <button className={tab === 'checks' ? 'active' : ''} onClick={() => setTab('checks')}>
          Checks<span className="count">
            {(run.validation_status ? 1 : 0) + guards.length || '—'}
          </span>
        </button>
        <button className={tab === 'snapshot' ? 'active' : ''} onClick={() => setTab('snapshot')}>
          Snapshot
        </button>
      </div>

      {tab === 'prompt' && (
      <section className="section">
        {/* Rendered system/user prompts (composed for this run) */}
        {renderedPrompt ? (
          <>
            <details className="code-block" style={{ marginBottom: 8 }}>
              <summary className="code-block-bar">
                <strong>System prompt</strong>
                <span className="dim" style={{ marginLeft: 8 }}>
                  {renderedPrompt.system.length.toLocaleString()} chars
                </span>
              </summary>
              <pre style={{ margin: 0, padding: 10, maxHeight: '50vh', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {renderedPrompt.system}
              </pre>
            </details>
            <details className="code-block" style={{ marginBottom: 8 }} open>
              <summary className="code-block-bar">
                <strong>User message</strong>
                <span className="dim" style={{ marginLeft: 8 }}>
                  {renderedPrompt.user.length.toLocaleString()} chars
                </span>
              </summary>
              <pre style={{ margin: 0, padding: 10, maxHeight: '50vh', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {renderedPrompt.user}
              </pre>
            </details>
            {renderedPrompt.schema != null && (
              <details className="code-block" style={{ marginBottom: 8 }}>
                <summary className="code-block-bar">Output schema</summary>
                <pre style={{ margin: 0, padding: 10, maxHeight: '40vh', overflow: 'auto' }}>
                  {JSON.stringify(renderedPrompt.schema, null, 2)}
                </pre>
              </details>
            )}
          </>
        ) : (
          <p className="dim" style={{ margin: '0 0 10px', fontSize: 12 }}>
            rendered prompt not captured for this run — only embedded runners
            (pydantic-ai, etc.) post system/user back. The assembled-prompt
            fragments below show what the runner actually concatenated.
          </p>
        )}

        {/* Variables — small KV table */}
        {variablesEntries.length > 0 && (
          <details open style={{ marginBottom: 8 }}>
            <summary style={{ cursor: 'pointer', fontSize: 13, marginBottom: 6 }}>
              <strong>Variables</strong>
              <span className="dim" style={{ marginLeft: 6, fontSize: 11 }}>
                {variablesEntries.length} sent by caller
              </span>
            </summary>
            <table className="kv-table">
              <tbody>
                {variablesEntries.map(([k, v]) => {
                  const str = typeof v === 'string' ? v : JSON.stringify(v, null, 2);
                  return (
                    <tr key={k}>
                      <td>{k} <span className="dim" style={{ fontSize: 10 }}>{str.length.toLocaleString()}</span></td>
                      <td><div className="clip">{str}</div></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </details>
        )}

        {/* Input (raw) — collapsed if same as variables */}
        {inputPretty.text ? (
          <details
            className="code-block"
            style={{ marginBottom: 8 }}
            open={!inputIsSameAsVariables && variablesEntries.length === 0}
          >
            <summary className="code-block-bar">
              <strong>Input (raw)</strong>
              <span className="dim" style={{ marginLeft: 8 }}>
                {inputPretty.isJson ? 'JSON · ' : ''}
                {inputPretty.text.length.toLocaleString()} chars
                {inputIsSameAsVariables && ' · same as variables'}
              </span>
            </summary>
            <pre style={{ margin: 0, padding: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {inputPretty.text}
            </pre>
          </details>
        ) : null}

        {/* Output */}
        {run.output ? (
          <details className="code-block" style={{ marginBottom: 8 }} open>
            <summary className="code-block-bar">
              <strong>Output</strong>
              <span className="dim" style={{ marginLeft: 8 }}>
                {outputPretty.isJson ? 'JSON · ' : ''}
                {outputPretty.text.length.toLocaleString()} chars
              </span>
            </summary>
            <pre style={{ margin: 0, padding: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {outputPretty.text}
            </pre>
          </details>
        ) : (
          <p className="dim" style={{ margin: '6px 0 0', fontSize: 12 }}>
            no output captured{run.status === 'running' ? ' yet' : ''}.
          </p>
        )}

        {/* Assembled prompt fragments (collapsed — debugging detail) */}
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: 'pointer', fontSize: 13 }}>
            <strong>Assembled prompt fragments</strong>
            <span className="dim" style={{ marginLeft: 6, fontSize: 11 }}>
              {promptDoc
                ? `${promptDoc.fragments.length} fragments · ${fmtBytes(promptDoc.total_bytes)}`
                : 'not captured'}
              {runnerKind && ` · runner ${runnerKind}`}
            </span>
          </summary>
          <div style={{ marginTop: 8 }}>
            {promptDoc ? (
              <div className="code-block">
                {promptDoc.fragments.map((f, i) => (
                  <FragmentRow key={i} f={f} total={promptDoc.total_bytes} />
                ))}
              </div>
            ) : (
              <p className="dim" style={{ margin: 0, fontSize: 12 }}>
                fragments not captured (older run or capture failed)
              </p>
            )}
          </div>
        </details>
      </section>
      )}

      {tab === 'conversation' && (
        <section className="section">
          <div className="row between" style={{ marginBottom: 8 }}>
            <h2 style={{ border: 'none', margin: 0 }}>
              {eventView === 'conversation' ? 'Conversation' : 'Event stream'}
              {isLive && <span className="pill running" style={{ marginLeft: 8, fontSize: 10 }}>live</span>}
            </h2>
            <div className="row">
              <div className="range-toggle">
                <button
                  className={eventView === 'conversation' ? 'active' : ''}
                  onClick={() => setEventView('conversation')}
                >
                  conversation
                </button>
                <button
                  className={eventView === 'events' ? 'active' : ''}
                  onClick={() => setEventView('events')}
                >
                  raw events
                </button>
              </div>
              <button
                style={{ fontSize: 11, padding: '3px 8px' }}
                onClick={() => {
                  setEventsLoading(true);
                  api.getTranscript(id)
                    .then((evs) => { setEvents(evs as StreamEvent[]); setEventsLoading(false); })
                    .catch(() => { setEventsError('failed to load transcript'); setEventsLoading(false); });
                }}
              >
                refresh
              </button>
            </div>
          </div>
          {eventsLoading ? (
            <p className="dim" style={{ margin: 0, textAlign: 'center', padding: 20 }}>loading events…</p>
          ) : eventsError ? (
            <p className="dim" style={{ margin: 0, textAlign: 'center', padding: 20, color: 'var(--red)' }}>{eventsError}</p>
          ) : eventView === 'conversation' ? (
            <ConversationView events={events} />
          ) : (
            <EventStream events={events} isLive={isLive} />
          )}
        </section>
      )}

      {tab === 'tools' && <ToolCallsSection events={events} />}

      {tab === 'checks' && (
        <>
          <section className="section">
            <h2 style={{ borderBottom: 'none' }}>
              Validation{' '}
              {run.validation_status && (
                <span className={`pill ${run.validation_status === 'ok' ? 'ok' : run.validation_status === 'warn' ? 'running' : 'error'}`}>
                  {run.validation_status}
                </span>
              )}
            </h2>
            {run.validation_status ? (
              run.validation_errors ? (
                <CodeBlock value={run.validation_errors} language="json" />
              ) : (
                <p className="dim" style={{ margin: 0, fontSize: 12 }}>passed with no errors</p>
              )
            ) : (
              <p className="dim" style={{ margin: 0, fontSize: 12 }}>
                no output schema configured for this agent — set
                {' '}<code>runner.output_schema_path</code> in the agent config
                to enable jsonschema/pydantic validation with retries.
              </p>
            )}
          </section>

          <section className="section">
            <h2 style={{ borderBottom: 'none' }}>
              Guardrails {guards.length > 0 && <span className="dim">({guards.length})</span>}
            </h2>
            {guards.length === 0 ? (
              <p className="dim" style={{ margin: 0, fontSize: 12 }}>
                no guardrails ran for this agent — add a <code>guardrails</code> entry
                in the agent config to record post-run observational checks here
                (e.g. cost-bound, schema-shape, custom python).
              </p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>#</th><th>Name</th><th>Result</th><th>Message</th><th>At</th>
                  </tr>
                </thead>
                <tbody>
                  {guards.map((g) => (
                    <tr key={g.id}>
                      <td className="dim">{g.attempt}</td>
                      <td><code>{g.name}</code></td>
                      <td>{g.ok ? <span className="pill ok">ok</span> : <span className="pill error">fail</span>}</td>
                      <td style={{ whiteSpace: 'pre-wrap' }}>{g.message ?? ''}</td>
                      <td className="dim" title={g.created_at}>{fmtRelative(g.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}

      {tab === 'snapshot' && (
        <section className="section">
          <h2 style={{ border: 'none', margin: 0, marginBottom: 6 }}>
            Composition Snapshot <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· recipe + references at run time</span>
          </h2>
          {run.composition_snapshot ? (
            <dl className="dl">
              {run.composition_snapshot.bundle_sha !== undefined && run.composition_snapshot.bundle_sha !== null && (
                <><dt>Bundle SHA</dt><dd><code>{String(run.composition_snapshot.bundle_sha)}</code></dd></>
              )}
              {run.composition_snapshot.schema_sha !== undefined && run.composition_snapshot.schema_sha !== null && (
                <><dt>Schema SHA</dt><dd><code>{String(run.composition_snapshot.schema_sha)}</code></dd></>
              )}
              {Array.isArray(run.composition_snapshot.references) && (
                <>
                  <dt>References</dt>
                  <dd>
                    <ul style={{ margin: 0, paddingLeft: 16 }}>
                      {run.composition_snapshot.references.map((ref: unknown, i: number) => (
                        <li key={i}><code>{typeof ref === 'string' ? ref : (JSON.stringify(ref) ?? '')}</code></li>
                      ))}
                    </ul>
                  </dd>
                </>
              )}
            </dl>
          ) : (
            <p className="dim" style={{ margin: 0, fontSize: 12 }}>
              composition snapshot not captured for this run — populated when
              the runner uses bundled references (see <code>composition</code>
              in the agent config). Snapshot pins the exact bundle+schema SHAs
              used so a rerun is byte-reproducible.
            </p>
          )}
        </section>
      )}

      {/* ── Comments (always at the bottom, across tabs) ─────────────── */}
      <RunCommentThread runId={id} />
    </div>
  );
}

