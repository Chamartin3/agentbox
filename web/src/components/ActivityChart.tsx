import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CHART_STATUSES, STATUS_COLORS } from '../theme/statusColors';

export interface ActivitySeriesPoint {
  date: string;
  runs?: number;
  ok?: number;
  error?: number;
  failed?: number;
  timeout?: number;
  incomplete?: number;
  running?: number;
}

interface Props {
  series: ActivitySeriesPoint[];
  rangeDays?: number;
  height?: number;
}

function fmtDateTick(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export default function ActivityChart({ series, rangeDays, height = 220 }: Props) {
  const padded = useMemo(() => {
    if (!rangeDays) return series;
    const byDate = new Map(series.map((p) => [p.date, p]));
    const empty = {
      runs: 0,
      failures: 0,
      running: 0,
      ok: 0,
      error: 0,
      failed: 0,
      timeout: 0,
      incomplete: 0,
    };
    const out: Array<typeof empty & { date: string }> = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let i = rangeDays - 1; i >= 0; i -= 1) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      const hit = byDate.get(key);
      out.push((hit as never) ?? { date: key, ...empty });
    }
    return out;
  }, [series, rangeDays]);

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={padded} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <defs>
            {CHART_STATUSES.map((k) => (
              <linearGradient key={k} id={`fill-${k}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={STATUS_COLORS[k]} stopOpacity={0.7} />
                <stop offset="100%" stopColor={STATUS_COLORS[k]} stopOpacity={0.15} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
          <XAxis dataKey="date" tickFormatter={fmtDateTick} stroke="#8b949e" fontSize={11} />
          <YAxis allowDecimals={false} stroke="#8b949e" fontSize={11} />
          <Tooltip
            labelFormatter={(v) => new Date(v as string).toLocaleDateString()}
            contentStyle={{ background: '#161b22', border: '1px solid #30363d', fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />
          {CHART_STATUSES.map((k) => (
            <Area
              key={k}
              type="monotone"
              stackId="status"
              dataKey={k}
              stroke={STATUS_COLORS[k]}
              fill={`url(#fill-${k})`}
              name={k}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
