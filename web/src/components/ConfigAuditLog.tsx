import { useEffect, useState } from 'react';

interface ConfigEvent {
  id: number;
  agent_id: string;
  field: string;
  from_value: string | null;
  to_value: string | null;
  author: string;
  source: string;
  created_at: string;
}

interface ConfigAuditLogProps {
  agentId: string;
}

export default function ConfigAuditLog({ agentId }: ConfigAuditLogProps) {
  const [events, setEvents] = useState<ConfigEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/agents/${agentId}/config-events?limit=50`)
      .then((r) => r.json())
      .then((d) => setEvents(d.events ?? []))
      .catch(() => setEvents([]))
      .finally(() => setIsLoading(false));
  }, [agentId]);

  if (isLoading) return <div>Loading config history...</div>;
  if (events.length === 0) return <p style={{ color: '#888' }}>No configuration changes recorded.</p>;

  const fmtVal = (v: string | null) => {
    if (v === null) return '—';
    try { return JSON.stringify(JSON.parse(v)); } catch { return v; }
  };

  return (
    <div className="config-audit-log">
      <h4 style={{ marginBottom: '0.75rem' }}>Configuration Change History</h4>
      <div style={{ fontSize: '0.85rem' }}>
        {events.map((ev) => (
          <div key={ev.id} style={{ borderBottom: '1px solid #eee', padding: '0.5rem 0', display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
            <span style={{ color: '#888', whiteSpace: 'nowrap' }}>
              {new Date(ev.created_at).toLocaleString()}
            </span>
            <span>
              ⚙ <strong>{ev.field}</strong>: <code>{fmtVal(ev.from_value)}</code> → <code>{fmtVal(ev.to_value)}</code>
            </span>
            <span style={{ color: '#888', marginLeft: 'auto', whiteSpace: 'nowrap' }}>
              {ev.author}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
