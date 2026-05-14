interface Props {
  label: string;
  value: string;
  sub?: string;
}

export default function StatCard({ label, value, sub }: Props) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}
