import { Link } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Color maps — single source of truth for type/status palettes
// ---------------------------------------------------------------------------

export const TYPE_COLORS: Record<string, { bg: string; fg: string }> = {
  document: { bg: '#dbeafe', fg: '#1e3a8a' },
  folder: { bg: '#fef3c7', fg: '#92400e' },
  skill: { bg: '#dcfce7', fg: '#14532d' },
  schema: { bg: '#ede9fe', fg: '#4c1d95' },
  script: { bg: '#fee2e2', fg: '#7f1d1d' },
};

export const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  ok: { bg: '#dcfce7', fg: '#14532d' },
  running: { bg: '#fef3c7', fg: '#92400e' },
  error: { bg: '#fee2e2', fg: '#7f1d1d' },
  timeout: { bg: '#fed7aa', fg: '#7c2d12' },
  incomplete: { bg: '#e0e7ff', fg: '#3730a3' },
};

// ---------------------------------------------------------------------------
// TypePill — a colored pill with optional click handler
// ---------------------------------------------------------------------------

export interface TypePillProps {
  value: string;
  colors?: Record<string, { bg: string; fg: string }>;
  label?: string;
  onClick?: () => void;
}

export function TypePill({ value, colors, label, onClick }: TypePillProps) {
  const c = (colors || TYPE_COLORS)[value] || { bg: '#f3f4f6', fg: '#374151' };
  const text = label || value;

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="pill"
        style={{
          background: c.bg,
          color: c.fg,
          border: 'none',
          cursor: 'pointer',
          padding: '2px 8px',
          fontSize: 12,
        }}
        title={`filter by ${text}`}
      >
        {text}
      </button>
    );
  }

  return (
    <span
      className="pill"
      style={{ background: c.bg, color: c.fg, padding: '2px 8px', fontSize: 12 }}
    >
      {text}
    </span>
  );
}

// ---------------------------------------------------------------------------
// FilterChipBar — "active filters:" row with removable chips
// ---------------------------------------------------------------------------

export interface FilterChip {
  key: string;
  label: string;
  clear: () => void;
}

export interface FilterChipBarProps {
  chips: FilterChip[];
}

export function FilterChipBar({ chips }: FilterChipBarProps) {
  if (chips.length === 0) return null;

  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      <span className="dim" style={{ fontSize: 12 }}>active filters:</span>
      {chips.map((c) => (
        <span
          key={c.key}
          style={{
            padding: '2px 8px',
            fontSize: 11,
            background: '#f3f4f6',
            borderRadius: 12,
            display: 'inline-flex',
            gap: 4,
            alignItems: 'center',
          }}
        >
          {c.label}
          <button
            type="button"
            onClick={c.clear}
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontSize: 12,
              lineHeight: 1,
              padding: 0,
            }}
            aria-label={`clear ${c.label}`}
          >
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NameCell — standard two-line name pattern (bold link + dim mono sub-line)
// ---------------------------------------------------------------------------

export interface NameCellProps {
  to: string;
  title: string;
  sub?: string;
  description?: string;
}

export function NameCell({ to, title, sub, description }: NameCellProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Link to={to} style={{ fontWeight: 600 }}>
        {title}
      </Link>
      {sub ? (
        <span className="dim" style={{ fontSize: 11, fontFamily: 'monospace' }}>
          {sub}
        </span>
      ) : null}
      {description ? (
        <span className="dim" style={{ fontSize: 12 }}>
          {description.length > 80
            ? `${description.slice(0, 80)}…`
            : description}
        </span>
      ) : null}
    </div>
  );
}
