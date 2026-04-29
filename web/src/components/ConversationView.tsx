import { useMemo, useState } from 'react';

export interface StreamEvent {
  type: string;
  [k: string]: unknown;
}

interface ConversationMessage {
  id: string;
  role: 'assistant' | 'user' | 'system' | 'tool' | 'meta';
  content: React.ReactNode;
  ts?: string;
  meta?: Record<string, unknown>;
  // True when this message was built from incremental delta TextEvents.
  // A subsequent non-delta TextEvent for the same role REPLACES it
  // (the backend emits a consolidated/fence-stripped final text).
  fromDelta?: boolean;
}

function fmtDt(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function buildConversation(events: StreamEvent[]): ConversationMessage[] {
  const msgs: ConversationMessage[] = [];
  let pendingToolCalls: StreamEvent[] = [];

  for (const ev of events) {
    const t = String(ev.type || '');
    const ts = typeof ev.ts === 'string' ? ev.ts : undefined;

    switch (t) {
      case 'thinking': {
        const text = String(ev.text || '');
        if (!text.trim()) continue;
        msgs.push({
          id: `${msgs.length}-thinking`,
          role: 'meta',
          ts,
          content: (
            <details className="conversation-thinking">
              <summary className="conversation-thinking-header">
                <span className="conversation-role">thinking</span>
                <span className="dim">{text.length} chars</span>
              </summary>
              <pre className="conversation-thinking-body">{text}</pre>
            </details>
          ),
        });
        break;
      }
      case 'text': {
        const role = String(ev.role || 'assistant');
        const text = String(ev.text || '');
        if (!text.trim()) continue;
        const isDelta = Boolean(ev.delta);
        const last = msgs[msgs.length - 1];
        // Non-delta following deltas → consolidated final text, replace
        // the streamed-in-progress message rather than duplicating it.
        if (!isDelta && last && last.role === role && role === 'assistant' && last.fromDelta) {
          last.content = text;
          last.ts = ts;
          last.fromDelta = false;
        } else if (last && last.role === role && role === 'assistant') {
          last.content = (
            <>
              {last.content}
              {text}
            </>
          );
          last.ts = ts;
          if (isDelta) last.fromDelta = true;
        } else {
          msgs.push({
            id: `${msgs.length}-text`,
            role: role as 'assistant' | 'user' | 'system',
            content: text,
            ts,
            fromDelta: isDelta,
          });
        }
        break;
      }
      case 'tool_call': {
        pendingToolCalls.push(ev);
        break;
      }
      case 'tool_result': {
        const callId = String(ev.call_id || '');
        const tool = String(ev.tool || '');
        const matched = pendingToolCalls.find((c) => String(c.call_id || '') === callId && String(c.tool || '') === tool);
        if (matched) {
          pendingToolCalls = pendingToolCalls.filter((c) => c !== matched);
        }
        msgs.push({
          id: `${msgs.length}-tool`,
          role: 'tool',
          ts,
          meta: { tool, arguments: matched?.arguments, ok: ev.ok, result_excerpt: ev.result_excerpt },
          content: (
            <div className="conversation-tool">
              <div className="conversation-tool-header">
                <code>{tool}</code>
                {ev.ok ? <span className="pill ok">ok</span> : <span className="pill error">fail</span>}
              </div>
              {matched?.arguments && (
                <details>
                  <summary className="dim" style={{ fontSize: 11, cursor: 'pointer' }}>arguments</summary>
                  <pre style={{ fontSize: 11, margin: '4px 0 0' }}>{JSON.stringify(matched.arguments, null, 2)}</pre>
                </details>
              )}
              {ev.result_excerpt && (
                <details>
                  <summary className="dim" style={{ fontSize: 11, cursor: 'pointer' }}>result</summary>
                  <pre style={{ fontSize: 11, margin: '4px 0 0' }}>{String(ev.result_excerpt)}</pre>
                </details>
              )}
            </div>
          ),
        });
        break;
      }
      case 'log': {
        const level = String(ev.level || 'info');
        const message = String(ev.message || '');
        if (level === 'debug') continue;
        const isVerbose = level === 'error' || level === 'warn';
        msgs.push({
          id: `${msgs.length}-log`,
          role: 'meta',
          ts,
          content: isVerbose ? (
            <details className={`conversation-log conversation-log-${level}`}>
              <summary className="conversation-log-summary">
                <span className="conversation-log-level">{level}</span>
                <span className="dim" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {message.slice(0, 80)}{message.length > 80 ? '...' : ''}
                </span>
              </summary>
              <pre className="conversation-log-body">{message}</pre>
            </details>
          ) : (
            <div className={`conversation-log conversation-log-${level}`}>
              <span className="conversation-log-level">{level}</span>
              <span>{message}</span>
            </div>
          ),
        });
        break;
      }
      case 'retry': {
        const errText = ev.error ? String(ev.error) : '';
        msgs.push({
          id: `${msgs.length}-retry`,
          role: 'meta',
          ts,
          content: errText ? (
            <details className="conversation-retry">
              <summary className="conversation-retry-summary">
                <span className="pill running" style={{ fontSize: 10 }}>retry #{ev.attempt}</span>
                <span className="dim">{ev.reason}</span>
                <span className="dim" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {errText.slice(0, 60)}{errText.length > 60 ? '...' : ''}
                </span>
              </summary>
              <pre className="conversation-retry-body">{errText}</pre>
            </details>
          ) : (
            <div className="conversation-retry">
              <span className="pill running" style={{ fontSize: 10 }}>retry #{ev.attempt}</span>
              <span className="dim">{ev.reason}</span>
            </div>
          ),
        });
        break;
      }
      case 'usage': {
        msgs.push({
          id: `${msgs.length}-usage`,
          role: 'meta',
          ts,
          content: (
            <div className="conversation-usage">
              <span className="dim">tokens</span>
              <span>in {ev.input_tokens ?? 0}</span>
              <span>out {ev.output_tokens ?? 0}</span>
              {ev.cost_usd !== null && ev.cost_usd !== undefined && <span>${Number(ev.cost_usd).toFixed(4)}</span>}
            </div>
          ),
        });
        break;
      }
      case 'guardrail': {
        msgs.push({
          id: `${msgs.length}-guardrail`,
          role: 'meta',
          ts,
          content: (
            <div className="conversation-guardrail">
              <span className="dim">guardrail</span>
              <code>{String(ev.name || '')}</code>
              {ev.ok ? <span className="pill ok">ok</span> : <span className="pill error">fail</span>}
            </div>
          ),
        });
        break;
      }
      case 'done': {
        msgs.push({
          id: `${msgs.length}-done`,
          role: 'meta',
          ts,
          content: (
            <div className="conversation-done">
              <span className={`pill ${ev.ok ? 'ok' : 'error'}`}>{ev.ok ? 'done' : String(ev.status || 'error')}</span>
              {ev.error && <span className="dim">{String(ev.error).slice(0, 200)}</span>}
            </div>
          ),
        });
        break;
      }
      case 'timeout': {
        msgs.push({
          id: `${msgs.length}-timeout`,
          role: 'meta',
          ts,
          content: (
            <details className="conversation-timeout">
              <summary className="conversation-timeout-summary">
                <span className="pill error" style={{ fontSize: 10 }}>timeout</span>
                <span className="dim">after {String(ev.timeout_seconds ?? '?')}s</span>
              </summary>
              {ev.error && <pre className="conversation-timeout-body">{String(ev.error)}</pre>}
            </details>
          ),
        });
        break;
      }
      default:
        break;
    }
  }

  // Flush any unmatched tool calls
  for (const tc of pendingToolCalls) {
    msgs.push({
      id: `${msgs.length}-tool-pending`,
      role: 'tool',
      content: (
        <div className="conversation-tool">
          <div className="conversation-tool-header">
            <code>{String(tc.tool || '')}</code>
            <span className="dim">…</span>
          </div>
          {tc.arguments && (
            <details>
              <summary className="dim" style={{ fontSize: 11, cursor: 'pointer' }}>arguments</summary>
              <pre style={{ fontSize: 11, margin: '4px 0 0' }}>{JSON.stringify(tc.arguments, null, 2)}</pre>
            </details>
          )}
        </div>
      ),
    });
  }

  return msgs;
}

export default function ConversationView({ events }: { events: StreamEvent[] }) {
  const messages = useMemo(() => buildConversation(events), [events]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (messages.length === 0) {
    return <div className="conversation-empty">no messages yet</div>;
  }

  return (
    <div className="conversation">
      {messages.map((m) => {
        const isOpen = expanded.has(m.id);
        switch (m.role) {
          case 'assistant':
            return (
              <div key={m.id} className="conversation-turn assistant">
                <div className="conversation-turn-header">
                  <span className="conversation-role">assistant</span>
                  {m.ts && <span className="conversation-ts">{fmtDt(m.ts)}</span>}
                </div>
                <div className="conversation-turn-body">
                  <pre className="conversation-text">{m.content}</pre>
                </div>
              </div>
            );
          case 'user':
            return (
              <div key={m.id} className="conversation-turn user">
                <div className="conversation-turn-header">
                  <span className="conversation-role">user</span>
                  {m.ts && <span className="conversation-ts">{fmtDt(m.ts)}</span>}
                </div>
                <div className="conversation-turn-body">
                  <pre className="conversation-text">{m.content}</pre>
                </div>
              </div>
            );
          case 'system':
            return (
              <div key={m.id} className="conversation-turn system">
                <div className="conversation-turn-header">
                  <span className="conversation-role">system</span>
                  {m.ts && <span className="conversation-ts">{fmtDt(m.ts)}</span>}
                </div>
                <div className="conversation-turn-body">
                  <pre className="conversation-text">{m.content}</pre>
                </div>
              </div>
            );
          case 'tool':
            return (
              <div key={m.id} className="conversation-turn tool">
                {m.content}
              </div>
            );
          case 'meta':
            return (
              <div key={m.id} className="conversation-meta">
                {m.content}
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}
