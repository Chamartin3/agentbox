import { RunsStats } from '../../api/client';
import { fmtMs, fmtNum } from '../../util/format';
import StatCard from './StatCard';
import ModelDonut from './charts/ModelDonut';
import StatusBar from './charts/StatusBar';
import TokensTimeseries from './charts/TokensTimeseries';
import TopAgentsBar from './charts/TopAgentsBar';
import VersionBar from './charts/VersionBar';

interface Props {
  stats: RunsStats | null;
  scope?: 'global' | { agentId: string };
}

export default function RunsDashboard({ stats, scope }: Props) {
  if (!stats) return null;

  const { totals, by_agent, by_model, by_version, by_status, timeseries } = stats;
  const totalTokens = totals.input_tokens + totals.output_tokens;
  const avgTokens = totals.runs > 0 ? Math.round(totalTokens / totals.runs) : 0;
  const isScoped = typeof scope === 'object' && scope !== null;

  return (
    <div className="runs-dashboard">
      <div className="stat-grid">
        <StatCard label="Runs" value={fmtNum(totals.runs)} />
        <StatCard
          label="Avg Tokens / Run"
          value={fmtNum(avgTokens)}
          sub={`total ${fmtNum(totalTokens)}`}
        />
        <StatCard label="Avg Duration" value={fmtMs(totals.avg_duration_ms)} />
      </div>

      <div className="chart-grid">
        {isScoped ? (
          <VersionBar data={by_version} />
        ) : (
          <TopAgentsBar data={by_agent} />
        )}
        <ModelDonut data={by_model} />
        <StatusBar data={by_status} />
        <TokensTimeseries data={timeseries} />
      </div>
    </div>
  );
}
