export type ActivityRange = '7d' | '30d' | '90d';
export type AgentRunState = 'running' | 'succeeded' | 'failed' | 'timeout';

export interface AgentRun {
  id: string;
  action_name: string;
  backend: string;
  configured_model: string | null;
  reported_model: string | null;
  state: AgentRunState;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cache_creation_tokens: number | null;
  cost_usd: number | null;
  job_application_id?: number | null;
  num_turns?: number | null;
  summary?: string | null;
  error?: string | null;
  meta?: Record<string, unknown>;
  session_id?: string | null;
}

export interface ActivityTotals {
  runs: number;
  running: number;
  successes: number;
  failures: number;
  timeouts: number;
  failure_rate_pct: number;
  avg_duration_ms: number;
  total_duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface ActivityByAction {
  action_name: string;
  total: number;
  failures: number;
  avg_duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface ActivityByReportedModel {
  reported_model: string;
  total: number;
  failures: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface ActivitySummary {
  totals: ActivityTotals;
  series: Array<{
    date: string;
    runs: number;
    failures: number;
    running: number;
    ok: number;
    error: number;
    failed: number;
    timeout: number;
    incomplete: number;
  }>;
  by_action: ActivityByAction[];
  by_reported_model: ActivityByReportedModel[];
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return (await resp.json()) as T;
}

export const activityApi = {
  summary(params: { range: ActivityRange; action?: string; executor?: string }) {
    const qs = new URLSearchParams({ range: params.range });
    if (params.action) qs.set('action', params.action);
    if (params.executor) qs.set('executor', params.executor);
    return get<ActivitySummary>(`/api/activity/summary?${qs}`);
  },
  runs(params: {
    range: ActivityRange;
    action?: string;
    executor?: string;
    state?: AgentRunState;
    limit?: number;
  }) {
    const qs = new URLSearchParams({ range: params.range });
    if (params.action) qs.set('action', params.action);
    if (params.executor) qs.set('executor', params.executor);
    if (params.state) qs.set('state', params.state);
    if (params.limit) qs.set('limit', String(params.limit));
    return get<{ results: AgentRun[]; total: number }>(`/api/activity/runs?${qs}`);
  },
};
