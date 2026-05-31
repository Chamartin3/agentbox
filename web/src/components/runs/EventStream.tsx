import { useEffect, useMemo, useRef, useState } from 'react';
import {
  getEventMeta,
  summarizeEvent,
  type LooseStreamEvent,
} from '../../api/events';
import { fmtDt, fmtRelativeShort, fmtTimeMs } from '../../util/format';

// Backwards-compatible alias for existing callers (RunDetailPage etc.).
// New code should import RunEvent / UiRunEvent from ../api/events instead.
export type StreamEvent = LooseStreamEvent;

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

  // Coalesce consecutive streaming-delta events (text/thinking) so each
  // streamed token doesn't produce its own row. A run with thousands of
  // 1-char deltas would otherwise render thousands of components.
  const coalesced = useMemo(() => {
    const out: StreamEvent[] = [];
    for (const ev of events) {
      const t = String(ev.type || '');
      const isDelta =
        (t === 'text' || t === 'thinking') && Boolean(ev.delta);
      if (isDelta && out.length > 0) {
        const prev = out[out.length - 1];
        const prevIsDelta =
          String(prev.type || '') === t &&
          Boolean(prev.delta) &&
          (prev as { _coalesced?: boolean })._coalesced !== false &&
          String(prev.role ?? '') === String(ev.role ?? '');
        if (prevIsDelta) {
          // Merge into a single virtual event. Clone so we don't mutate
          // the parent's events array (kept referentially stable for memo).
          const merged: StreamEvent = {
            ...prev,
            text: String(prev.text ?? '') + String(ev.text ?? ''),
            ts: prev.ts ?? ev.ts,
            _coalesced: true,
            _coalesced_count: Number((prev as { _coalesced_count?: number })._coalesced_count ?? 1) + 1,
          };
          out[out.length - 1] = merged;
          continue;
        }
      }
      out.push(ev);
    }
    return out;
  }, [events]);

  // Build type counts.
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const ev of coalesced) {
      const t = String(ev.type || 'unknown');
      c[t] = (c[t] ?? 0) + 1;
    }
    return c;
  }, [coalesced]);

  const allTypes = useMemo(() => Object.keys(counts).sort(), [counts]);

  // If no explicit filter is set, show all types.
  const visibleTypes = activeTypes.size === 0 ? new Set(allTypes) : activeTypes;

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return coalesced
      .map((ev, idx) => ({ ev, idx }))
      .filter(({ ev }) => {
        const t = String(ev.type || '');
        if (!visibleTypes.has(t)) return false;
        if (!q) return true;
        return JSON.stringify(ev).toLowerCase().includes(q);
      });
  }, [coalesced, visibleTypes, search]);

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
            const meta = getEventMeta(type);
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
            const meta = getEventMeta(type);
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
                  <span className="event-ts" title={ts ? fmtDt(ts) : ''}>
                    {ts ? fmtTimeMs(ts) : ''}
                  </span>
                  <span className="event-relative">{ts ? fmtRelativeShort(ts) : ''}</span>
                  <span className="event-summary">{summary}</span>
                  {(ev as { _coalesced_count?: number })._coalesced_count && (
                    <span className="dim" style={{ fontSize: 10, marginLeft: 4 }}>
                      ×{String((ev as { _coalesced_count?: number })._coalesced_count)}
                    </span>
                  )}
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
          {coalesced.length !== events.length && (
            <> · {events.length - coalesced.length} deltas coalesced</>
          )}
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
