import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AgentDef, GuardrailRow, PromptFragment, RunPromptDoc, RunRecord, UsageRecord, api } from '../api/client';
import EventStream from '../components/EventStream';
import ConversationView from '../components/ConversationView';
import RunsTable from '../components/RunsTable';
import RunCommentThread from '../components/RunCommentThread';

interface StreamEvent {
  type: string;
  [k: string]: unknown;
}

// ────────────────────────────────────────────────────────────────── formatters

function fmtDt(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : '—';
}
function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  if (diff < 0) return 'in the future';
  const s = Math.floor(diff / 1000);
  if (s < 45) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  if (d < 30) return `${Math.floor(d / 7)}w ago`;
  return `${Math.floor(d / 30)}mo ago`;
}
function fmtMs(ms: number | null | undefined): string {
  if (!ms && ms !== 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}
function fmtNum(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : n.toLocaleString();
}
function fmtCost(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n === 0) return '$0';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}
function durationMs(r: RunRecord): number | null {
  if (!r.finished_at) return null;
  return new Date(r.finished_at).getTime() - new Date(r.created_at).getTime();
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

function PromptFragmentsSection({
  doc,
  runnerKind,
}: {
  doc: RunPromptDoc | null;
  runnerKind: string | null;
}) {
  if (!doc) {
    return (
      <section className="section">
        <h2 style={{ borderBottom: 'none' }}>Assembled prompt</h2>
        <p className="dim" style={{ margin: 0 }}>
          not captured for this run (older run or capture failed)
        </p>
      </section>
    );
  }
  const total = doc.total_bytes;
  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h2 style={{ border: 'none', margin: 0 }}>
          Assembled prompt{' '}
          <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
            · {doc.fragments.length} fragments · {fmtBytes(total)} total
            {runnerKind && <> · runner {runnerKind}</>}
          </span>
        </h2>
      </div>
      <div className="code-block">
        {doc.fragments.map((f, i) => (
          <FragmentRow key={i} f={f} total={total} />
        ))}
      </div>
    </section>
  );
}

// ──────────────────────────────────────────────────────────────────── page

export default function RunDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rerunning, setRerunning] = useState(false);
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

  if (!run) return <p className="dim">loading…</p>;

  return (
    <div className="stack">
      {/* ── header ───────────────────────────────────────────────────── */}
      <div className="run-header">
        <div>
          <div className="dim" style={{ fontSize: 11 }}>
            <Link to="/" className="dim">runs</Link>
            <span style={{ margin: '0 6px' }}>/</span>
            <code style={{ fontSize: 11 }}>{id}</code>
          </div>
          <h1 style={{ margin: '6px 0 0' }}>
            <Link to={`/agents/${run.agent_id}`}>{run.agent_id}</Link>
          </h1>
          <div className="dim" style={{ fontSize: 12, marginTop: 4 }}>
            {agent?.description}
          </div>
        </div>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
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
          <StatusPill status={run.status} />
        </div>
      </div>

      {/* ── status + metadata table ──────────────────────────────────── */}
      <RunsTable
        items={[{
          id: run.id,
          agent_id: run.agent_id,
          status: run.status,
          started_at: run.created_at,
          finished_at: run.finished_at,
          duration_ms: duration,
          executor: agent?.runner?.kind ?? null,
          model: usage?.model ?? agent?.runner?.model ?? null,
          input_tokens: usage?.input_tokens ?? null,
          output_tokens: usage?.output_tokens ?? null,
          cache_read_tokens: usage?.cache_read_tokens ?? null,
          cache_creation_tokens: usage?.cache_write_tokens ?? null,
          cost_usd: usage?.cost_usd ?? null,
        }]}
        columns={['run', 'agent', 'status', 'model', 'runner', 'duration', 'tokens', 'cost']}
        emptyMessage=""
      />

      {/* ── context tags (non-duplicating the RunsTable above) ────────── */}
      <div className="meta-tags">
        <Tag label="started" value={fmtRelative(run.created_at)} tone="accent" />
        {run.finished_at && <Tag label="finished" value={fmtRelative(run.finished_at)} />}
        {agent?.session_mode && <Tag label="session" value={agent.session_mode} />}
        {agent?.workspace === '<ephemeral>'
          ? <Tag label="workspace" value="ephemeral" />
          : agent?.workspace && <Tag label="workspace" value={agent.workspace} tone="mono" />}
        {run.session_id && <Tag label="session_id" value={run.session_id.slice(0, 8)} tone="mono" />}
      </div>

      {/* ── error card (collapsed by default) ─────────────────────────── */}
      {run.error && (
        <details className="section error-card" style={{ padding: 0 }}>
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

      {/* ── KPI cards ────────────────────────────────────────────────── */}
      <div className="kpi-grid">
        <div className="kpi">
          <div className="kpi-label">Duration</div>
          <div className="kpi-value">{fmtMs(duration)}</div>
          <div className="kpi-sub" title={run.created_at}>
            started {fmtRelative(run.created_at)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Tokens</div>
          <div className="kpi-value">{fmtNum(tokens)}</div>
          <div className="kpi-sub">
            in {fmtNum(usage?.input_tokens)} · out {fmtNum(usage?.output_tokens)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Cache</div>
          <div className="kpi-value">
            {fmtNum((usage?.cache_read_tokens ?? 0) + (usage?.cache_write_tokens ?? 0))}
          </div>
          <div className="kpi-sub">
            read {fmtNum(usage?.cache_read_tokens)} · write {fmtNum(usage?.cache_write_tokens)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Cost</div>
          <div className="kpi-value">{fmtCost(usage?.cost_usd)}</div>
          <div className="kpi-sub">{usage?.model ?? <span className="dim">no model</span>}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Events</div>
          <div className="kpi-value">{fmtNum(events.length)}</div>
          <div className="kpi-sub">{guards.length} guardrails</div>
        </div>
      </div>

      {/* ── Validation badge ─────────────────────────────────────────── */}
      {run.validation_status && (
        <section className="section">
          <div className="row between" style={{ marginBottom: 6 }}>
            <h2 style={{ border: 'none', margin: 0 }}>
              Validation{' '}
              <span className={`pill ${run.validation_status === 'ok' ? 'ok' : run.validation_status === 'warn' ? 'running' : 'error'}`}>
                {run.validation_status}
              </span>
            </h2>
          </div>
          {run.validation_errors && (
            <CodeBlock value={run.validation_errors} language="json" />
          )}
        </section>
      )}

      {/* ── Rendered Prompt ──────────────────────────────────────────── */}
      {run.rendered_prompt && (
        <section className="section">
          <h2 style={{ border: 'none', margin: 0, marginBottom: 8 }}>
            Rendered Prompt <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· composed for this run</span>
          </h2>
          <details className="code-block" style={{ marginBottom: 8 }}>
            <summary className="code-block-bar">System prompt</summary>
            <pre style={{ margin: 0, padding: 10 }}>{run.rendered_prompt.system}</pre>
          </details>
          <details className="code-block" style={{ marginBottom: 8 }}>
            <summary className="code-block-bar">User message</summary>
            <pre style={{ margin: 0, padding: 10 }}>{run.rendered_prompt.user}</pre>
          </details>
          {run.rendered_prompt.schema && (
            <details className="code-block">
              <summary className="code-block-bar">Output schema</summary>
              <pre style={{ margin: 0, padding: 10 }}>{JSON.stringify(run.rendered_prompt.schema, null, 2)}</pre>
            </details>
          )}
        </section>
      )}

      {/* ── Variables ────────────────────────────────────────────────── */}
      {run.variables && (
        <section className="section">
          <h2 style={{ border: 'none', margin: 0, marginBottom: 6 }}>
            Variables <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· what the caller sent</span>
          </h2>
          <CodeBlock value={JSON.stringify(run.variables, null, 2)} language="json" />
        </section>
      )}

      {/* ── Input ────────────────────────────────────────────────────── */}
      <section className="section">
        <div className="row between" style={{ marginBottom: 6 }}>
          <h2 style={{ border: 'none', margin: 0 }}>
            Input <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· what the agent received</span>
          </h2>
          {inputPretty.isJson && <span className="tag">JSON</span>}
        </div>
        {inputPretty.text
          ? <CodeBlock value={inputPretty.text} language={inputPretty.isJson ? 'json' : 'text'} />
          : <p className="dim" style={{ margin: 0 }}>(empty)</p>}
      </section>

      {/* ── Output ───────────────────────────────────────────────────── */}
      {run.output && (
        <section className="section">
          <div className="row between" style={{ marginBottom: 6 }}>
            <h2 style={{ border: 'none', margin: 0 }}>
              Output <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· final assistant text</span>
            </h2>
            {outputPretty.isJson && <span className="tag">JSON</span>}
          </div>
          <CodeBlock value={outputPretty.text} language={outputPretty.isJson ? 'json' : 'text'} />
        </section>
      )}

      {/* ── Assembled prompt ─────────────────────────────────────────── */}
      <PromptFragmentsSection doc={promptDoc} runnerKind={agent?.runner.kind ?? null} />

      {/* ── Tool calls ───────────────────────────────────────────────── */}
      <ToolCallsSection events={events} />

      {/* ── Event stream / Conversation ──────────────────────────────── */}
      <section className="section">
        <div className="row between" style={{ marginBottom: 8 }}>
          <h2 style={{ border: 'none', margin: 0 }}>
            {eventView === 'conversation' ? 'Conversation' : 'Event stream'}
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
                events
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

      {/* ── Guardrails ───────────────────────────────────────────────── */}
      <section className="section">
        <h2 style={{ borderBottom: 'none' }}>
          Guardrails {guards.length > 0 && <span className="dim">({guards.length})</span>}
        </h2>
        {guards.length === 0 ? (
          <p className="dim" style={{ margin: 0 }}>none ran for this agent</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Result</th>
                <th>Message</th>
                <th>At</th>
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

      {/* ── Composition snapshot ───────────────────────────────────── */}
      {run.composition_snapshot && (
        <section className="section">
          <h2 style={{ border: 'none', margin: 0, marginBottom: 6 }}>
            Composition Snapshot <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· recipe version</span>
          </h2>
          <dl className="dl">
            {run.composition_snapshot.bundle_sha && (
              <><dt>Bundle SHA</dt><dd><code>{String(run.composition_snapshot.bundle_sha)}</code></dd></>
            )}
            {run.composition_snapshot.schema_sha && (
              <><dt>Schema SHA</dt><dd><code>{String(run.composition_snapshot.schema_sha)}</code></dd></>
            )}
            {Array.isArray(run.composition_snapshot.references) && (
              <>
                <dt>References</dt>
                <dd>
                  <ul style={{ margin: 0, paddingLeft: 16 }}>
                    {run.composition_snapshot.references.map((ref: unknown, i: number) => (
                      <li key={i}><code>{typeof ref === 'string' ? ref : JSON.stringify(ref)}</code></li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
          </dl>
        </section>
      )}

      {/* ── Comments ──────────────────────────────────────────────── */}
      <RunCommentThread runId={id} />

      {/* ── Plumbing details (collapsed by default) ─────────────────── */}
      <details className="section" style={{ padding: '12px 16px' }}>
        <summary className="dim" style={{ cursor: 'pointer', fontWeight: 500 }}>
          Plumbing details
        </summary>
        <dl className="dl" style={{ marginTop: 12 }}>
          <dt>Run id</dt><dd><code>{run.id}</code></dd>
          <dt>Agent</dt><dd><Link to={`/agents/${run.agent_id}`}><code>{run.agent_id}</code></Link></dd>
          <dt>Session</dt><dd>{run.session_id ?? <span className="dim">—</span>}</dd>
          <dt>Workdir</dt><dd><code style={{ fontSize: 11 }}>{run.workdir ?? '—'}</code></dd>
          <dt>Transcript</dt><dd><code style={{ fontSize: 11 }}>{run.transcript_path ?? '—'}</code></dd>
          <dt>Started</dt><dd>{fmtDt(run.created_at)} <span className="dim">({fmtRelative(run.created_at)})</span></dd>
          <dt>Finished</dt><dd>{fmtDt(run.finished_at)} {run.finished_at && <span className="dim">({fmtRelative(run.finished_at)})</span>}</dd>
        </dl>
      </details>
    </div>
  );
}
