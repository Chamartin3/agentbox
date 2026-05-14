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
  data: Array<{ version: number; runs: number; tokens: number }>;
}

export default function VersionBar({ data }: Props) {
  const rows = data.map((d) => ({ ...d, label: `v${d.version}` }));
  return (
    <div className="chart-box">
      <h4>Runs by Version</h4>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={rows} margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="runs" fill="var(--blue)" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
