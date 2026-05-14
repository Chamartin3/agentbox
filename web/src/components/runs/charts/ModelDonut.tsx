import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

const COLORS = ['#3fb950', '#58a6ff', '#f0883e', '#f85149', '#d29922', '#8b949e', '#6e7681'];

interface Props {
  data: Array<{ model: string; runs: number }>;
}

export default function ModelDonut({ data }: Props) {
  if (data.length === 0) return null;
  return (
    <div className="chart-box">
      <h4>Model Mix</h4>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie data={data} dataKey="runs" nameKey="model" cx="50%" cy="50%" outerRadius={70} innerRadius={40}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
