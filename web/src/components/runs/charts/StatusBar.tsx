import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { statusColor } from '../../../theme/statusColors';

interface Props {
  data: Array<{ status: string; runs: number }>;
}

export default function StatusBar({ data }: Props) {
  return (
    <div className="chart-box">
      <h4>Status Breakdown</h4>
      <ResponsiveContainer width="100%" height={80}>
        <BarChart data={data} layout="vertical" margin={{ left: 80, right: 16, top: 4, bottom: 4 }}>
          <XAxis type="number" />
          <YAxis type="category" dataKey="status" tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="runs" radius={[0, 3, 3, 0]}>
            {data.map((r, i) => (
              <Cell key={i} fill={statusColor(r.status)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
