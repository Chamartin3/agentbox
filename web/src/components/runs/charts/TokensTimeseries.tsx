import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

interface Props {
  data: Array<{
    bucket: string;
    runs: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
  }>;
}

function fmtBucket(raw: string): string {
  if (!raw) return '';
  if (raw.length > 13) return raw.slice(5, 16); // "05-27T10:00"
  return raw.slice(5); // "05-27"
}

export default function TokensTimeseries({ data }: Props) {
  return (
    <div className="chart-box">
      <h4>Token Volume</h4>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data} margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="bucket" tickFormatter={fmtBucket} tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip labelFormatter={(v: string) => fmtBucket(v)} />
          <Area type="monotone" dataKey="input_tokens" stackId="1" stroke="var(--blue)" fill="var(--blue)" fillOpacity={0.2} name="Input" />
          <Area type="monotone" dataKey="output_tokens" stackId="1" stroke="var(--green)" fill="var(--green)" fillOpacity={0.2} name="Output" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
