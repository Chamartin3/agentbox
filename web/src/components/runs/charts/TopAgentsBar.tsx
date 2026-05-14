import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface Props {
  data: Array<{ agent_id: string; runs: number; tokens: number; cost_usd: number }>;
}

export default function TopAgentsBar({ data }: Props) {
  return (
    <div className="chart-box">
      <h4>Top Agents</h4>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} layout="vertical" margin={{ left: 80, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" />
          <YAxis type="category" dataKey="agent_id" tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="runs" fill="var(--blue)" radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
