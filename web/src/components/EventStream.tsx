import { useEffect, useMemo, useRef, useState } from 'react';

export interface StreamEvent {
  type: string;
  [k: string]: unknown;
}

function fmtDt(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
}

function fmtDtFull(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString() : '';
}

function fmtRelativeShort(iso: string | null | undefined): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

const EVENT_META: Record<string, { label: string; color: string; bg: string }> = {
  text:       { label: 'text',       color: '#c9d1d9', bg: 'rgba(201,209,217,0.08)' },
  log:        { label: 'log',        color: '#8b949e', bg: 'rgba(139,148,158,0.08)' },
  tool_call:  { label: 'call',       color: '#79c0ff', bg: 'rgba(121,192,255,0.10)' },
  tool_result:{ label: 'result',     color: '#3fb950', bg: 'rgba(63,185,80,0.10)' },
  usage:      { label: 'usage',      color: '#d29922', bg: 'rgba(210,153,34,0.10)' },
  guardrail:  { label: 'guardrail',  color: '#d2a8ff', bg: 'rgba(210,168,255,0.10)' },
  done:       { label: 'done',       color: '#58a6ff', bg: 'rgba(88,166,255,0.10)' },
  retry:      { label: 'retry',      color: '#f0883e', bg: 'rgba(240,136,62,0.10)' },
  thinking:   { label: 'thinking',   color: '#58a6ff', bg: 'rgba(88,166,255,0.10)' },
  timeout:    { label: 'timeout',    color: '#f0883e', bg: 'rgba(240,136,62,0.15)' },
  validation: { label: 'validation', color: '#d2a8ff', bg: 'rgba(210,168,255,0.10)' },
};

function getMeta(type: string) {
  return EVENT_META[type] ?? { label: type, color: 'var(--fg-muted)', bg: 'rgba(139,148,158,0.06)' };
}

function summarizeEvent(ev: StreamEvent): string {
  const t = String(ev.type || '');
  switch (t) {
    case 'text':
      return String(ev.text ?? '').slice(0, 180);
    case 'log':
      return `[${ev.level ?? ''}] ${String(ev.message ?? '').slice(0, 180)}`;
    case 'tool_call':
      return `${ev.tool ?? ''} ${JSON.stringify(ev.arguments ?? {}).slice(0, 140)}`;
    case 'tool_result':
      return `${ev.tool ?? ''} ok=${ev.ok}`;
    case 'usage':
      return `in=${ev.input_tokens ?? 0} out=${ev.output_tokens ?? 0} cost=$${ev.cost_usd ?? 0}`;
    case 'guardrail':
      return `${ev.name ?? ''} ok=${ev.ok}`;
    case 'done':
      return `status=${ev.status ?? ''}`;
    case 'retry':
      return `attempt=${ev.attempt ?? ''} reason=${ev.reason ?? ''}`;
    case 'thinking':
      return String(ev.text ?? '').slice(0, 180);
    case 'timeout':
      return `timeout after ${ev.timeout_seconds ?? '?'}s`;
    case 'validation':
      return `ok=${ev.ok} engine=${ev.engine ?? ''} mode=${ev.mode ?? ''} attempt=${ev.attempt ?? ''}${ev.error ? ` — ${String(ev.error).slice(0, 120)}` : ''}`;
    default:
      return JSON.stringify(ev).slice(0, 180);
  }
}

function eventKey(ev: StreamEvent, idx: number): string {
  return `${idx}-${ev.type}-${ev.ts ?? ''}`;
}

interface EventStreamProps {
  events: StreamEvent[];
  isLive?: boolean;
}

export default function EventStream({ events, isLive = false }: EventStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());

  // Build type counts.
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const ev of events) {
      const t = String(ev.type || 'unknown');
      c[t] = (c[t] ?? 0) + 1;
    }
    return c;
  }, [events]);

  const allTypes = useMemo(() => Object.keys(counts).sort(), [counts]);

  // If no explicit filter is set, show all types.
  const visibleTypes = activeTypes.size === 0 ? new Set(allTypes) : activeTypes;

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return events
      .map((ev, idx) => ({ ev, idx }))
      .filter(({ ev }) => {
        const t = String(ev.type || '');
        if (!visibleTypes.has(t)) return false;
        if (!q) return true;
        return JSON.stringify(ev).toLowerCase().includes(q);
      });
  }, [events, visibleTypes, search]);

  // Auto-scroll to bottom when new events arrive.
  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    const el = scrollRef.current;
    el.scrollTop = el.scrollHeight;
  }, [filtered, autoScroll]);

  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const expandAll = () => {
    setExpanded(new Set(filtered.map(({ ev, idx }) => eventKey(ev, idx))));
  };

  const collapseAll = () => setExpanded(new Set());

  return (
    <div className="event-stream">
      {/* Toolbar */}
      <div className="event-stream-toolbar">
        <div className="event-stream-chips">
          {allTypes.map((type) => {
            const meta = getMeta(type);
            const active = visibleTypes.has(type);
            return (
              <button
                key={type}
                className={`event-chip ${active ? 'active' : ''}`}
                onClick={() => toggleType(type)}
                title={`${active ? 'Hide' : 'Show'} ${type} events`}
                style={{
                  '--chip-color': meta.color,
                  '--chip-bg': meta.bg,
                } as React.CSSProperties}
              >
                <span className="event-chip-dot" />
                <span className="event-chip-label">{meta.label}</span>
                <span className="event-chip-count">{counts[type] ?? 0}</span>
              </button>
            );
          })}
        </div>

        <div className="event-stream-controls">
          {isLive && (
            <span className="event-live-indicator">
              <span className="event-live-dot" />
              live
            </span>
          )}
          <input
            type="text"
            placeholder="filter…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="event-search"
          />
          <button onClick={() => setAutoScroll((v) => !v)} className={autoScroll ? 'active' : ''}>
            auto-scroll
          </button>
          <button onClick={expandAll}>expand</button>
          <button onClick={collapseAll}>collapse</button>
        </div>
      </div>

      {/* Event list */}
      <div ref={scrollRef} className="event-stream-list">
        {filtered.length === 0 ? (
          <div className="event-empty">no events match the current filters</div>
        ) : (
          filtered.map(({ ev, idx }) => {
            const type = String(ev.type || '');
            const meta = getMeta(type);
            const key = eventKey(ev, idx);
            const isOpen = expanded.has(key);
            const ts = typeof ev.ts === 'string' ? ev.ts : undefined;
            const summary = summarizeEvent(ev);
            return (
              <div
                key={key}
                className={`event-row ${isOpen ? 'expanded' : ''}`}
                style={{
                  borderLeftColor: meta.color,
                  background: meta.bg,
                }}
              >
                <div className="event-row-header" onClick={() => toggleExpand(key)}>
                  <span className="event-type-pill" style={{ color: meta.color, borderColor: meta.color }}>
                    {meta.label}
                  </span>
                  <span className="event-ts" title={fmtDtFull(ts)}>
                    {ts ? fmtDt(ts) : ''}
                  </span>
                  <span className="event-relative">{ts ? fmtRelativeShort(ts) : ''}</span>
                  <span className="event-summary">{summary}</span>
                  <span className="event-toggle">{isOpen ? '−' : '+'}</span>
                </div>
                {isOpen && (
                  <div className="event-row-body">
                    <pre>{JSON.stringify(ev, null, 2)}</pre>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer stats */}
      <div className="event-stream-footer">
        <span className="dim">
          showing {filtered.length} of {events.length} events
        </span>
        {search && (
          <span className="dim">
            filter: “{search}”
          </span>
        )}
      </div>
    </div>
  );
}
