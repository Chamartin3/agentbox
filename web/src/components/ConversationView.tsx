import { useMemo } from 'react';
import type { LooseStreamEvent } from '../api/events';
import { fmtTime, prettyExcerpt } from '../util/format';

// Backwards-compatible alias. Prefer RunEvent/LooseStreamEvent from api/events.
export type StreamEvent = LooseStreamEvent;

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

function buildConversation(events: StreamEvent[]): ConversationMessage[] {
  const msgs: ConversationMessage[] = [];
  let pendingToolCalls: StreamEvent[] = [];
  const thinkingBuf: { texts: string[]; firstTs?: string } = { texts: [] };

  const flushThinking = () => {
    if (thinkingBuf.texts.length === 0) return;
    const joined = thinkingBuf.texts.join('').trim();
    const ts = thinkingBuf.firstTs;
    msgs.push({
      id: `${msgs.length}-thinking`,
      role: 'meta',
      ts,
      content: (
        <details className="conversation-thinking">
          <summary className="conversation-thinking-header">
            <span className="conversation-role">thinking</span>
            <span className="dim">{joined.length} chars</span>
          </summary>
          <pre className="conversation-thinking-body">{joined}</pre>
        </details>
      ),
    });
    thinkingBuf.texts = [];
    thinkingBuf.firstTs = undefined;
  };

  for (const ev of events) {
    const t = String(ev.type || '');
    const ts = typeof ev.ts === 'string' ? ev.ts : undefined;

    // Group consecutive thinking events (across interleaved usage/log noise too)
    // so the conversation stays readable. Non-noise events flush the buffer.
    if (t === 'thinking') {
      const text = String(ev.text || '');
      if (text.trim()) {
        if (thinkingBuf.texts.length === 0) thinkingBuf.firstTs = ts;
        thinkingBuf.texts.push(text);
      }
      continue;
    }
    if (t !== 'usage' && t !== 'log') {
      flushThinking();
    }

    switch (t) {
      case 'text': {
        const role = String(ev.role || 'assistant');
        const text = String(ev.text || '');
        if (!text.trim()) continue;
        // System and user turns are already shown in the Prompt section
        // of the run detail page — don't duplicate them here.
        if (role === 'system' || role === 'user') continue;
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
              {matched?.arguments !== undefined && matched?.arguments !== null && (
                <details>
                  <summary className="dim" style={{ fontSize: 11, cursor: 'pointer' }}>arguments</summary>
                  <pre style={{ fontSize: 11, margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>{prettyExcerpt(matched.arguments)}</pre>
                </details>
              )}
              {ev.result_excerpt !== undefined && ev.result_excerpt !== null && (
                <details>
                  <summary className="dim" style={{ fontSize: 11, cursor: 'pointer' }}>result</summary>
                  <pre style={{ fontSize: 11, margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>{prettyExcerpt(ev.result_excerpt)}</pre>
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
                <span className="pill running" style={{ fontSize: 10 }}>retry #{String(ev.attempt ?? '')}</span>
                <span className="dim">{String(ev.reason ?? '')}</span>
                <span className="dim" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {errText.slice(0, 60)}{errText.length > 60 ? '...' : ''}
                </span>
              </summary>
              <pre className="conversation-retry-body">{errText}</pre>
            </details>
          ) : (
            <div className="conversation-retry">
              <span className="pill running" style={{ fontSize: 10 }}>retry #{String(ev.attempt ?? '')}</span>
              <span className="dim">{String(ev.reason ?? '')}</span>
            </div>
          ),
        });
        break;
      }
      case 'validation': {
        const ok = Boolean(ev.ok);
        const errText = ev.error ? String(ev.error) : '';
        const engine = String(ev.engine ?? '');
        const mode = String(ev.mode ?? '');
        const attempt = String(ev.attempt ?? '');
        msgs.push({
          id: `${msgs.length}-validation`,
          role: 'meta',
          ts,
          content: ok ? (
            <div className="conversation-retry">
              <span className="pill ok" style={{ fontSize: 10 }}>validation ok</span>
              <span className="dim">attempt #{attempt}</span>
              <span className="dim">engine={engine}</span>
              <span className="dim">mode={mode}</span>
            </div>
          ) : (
            <details className="conversation-retry" open>
              <summary className="conversation-retry-summary">
                <span className="pill error" style={{ fontSize: 10 }}>validation fail</span>
                <span className="dim">attempt #{attempt}</span>
                <span className="dim">engine={engine}</span>
                <span className="dim">mode={mode}</span>
                <span className="dim" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {errText.slice(0, 80)}{errText.length > 80 ? '...' : ''}
                </span>
              </summary>
              <pre className="conversation-retry-body">{errText}</pre>
            </details>
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
              <span>in {Number(ev.input_tokens ?? 0)}</span>
              <span>out {Number(ev.output_tokens ?? 0)}</span>
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
              {ev.error !== undefined && ev.error !== null && <span className="dim">{String(ev.error).slice(0, 200)}</span>}
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
              {ev.error !== undefined && ev.error !== null && <pre className="conversation-timeout-body">{String(ev.error)}</pre>}
            </details>
          ),
        });
        break;
      }
      default:
        break;
    }
  }

  flushThinking();

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
          {tc.arguments !== undefined && tc.arguments !== null && (
            <details>
              <summary className="dim" style={{ fontSize: 11, cursor: 'pointer' }}>arguments</summary>
              <pre style={{ fontSize: 11, margin: '4px 0 0' }}>{JSON.stringify(tc.arguments, null, 2) ?? ''}</pre>
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
  if (messages.length === 0) {
    return <div className="conversation-empty">no messages yet</div>;
  }

  return (
    <div className="conversation">
      {messages.map((m) => {
        switch (m.role) {
          case 'assistant':
            return (
              <div key={m.id} className="conversation-turn assistant">
                <div className="conversation-turn-header">
                  <span className="conversation-role">assistant</span>
                  {m.ts && <span className="conversation-ts">{fmtTime(m.ts)}</span>}
                </div>
                <div className="conversation-turn-body">
                  <pre className="conversation-text">{typeof m.content === 'string' ? prettyExcerpt(m.content) : m.content}</pre>
                </div>
              </div>
            );
          case 'user':
            return (
              <div key={m.id} className="conversation-turn user">
                <div className="conversation-turn-header">
                  <span className="conversation-role">user</span>
                  {m.ts && <span className="conversation-ts">{fmtTime(m.ts)}</span>}
                </div>
                <div className="conversation-turn-body">
                  <pre className="conversation-text">{String(m.content)}</pre>
                </div>
              </div>
            );
          case 'system':
            return (
              <div key={m.id} className="conversation-turn system">
                <div className="conversation-turn-header">
                  <span className="conversation-role">system</span>
                  {m.ts && <span className="conversation-ts">{fmtTime(m.ts)}</span>}
                </div>
                <div className="conversation-turn-body">
                  <pre className="conversation-text">{String(m.content)}</pre>
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
