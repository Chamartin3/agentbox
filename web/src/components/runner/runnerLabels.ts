// Friendly harness names + implied providers for the CLI harnesses that
// bundle their own provider (so the provider fact is never blank).
const HARNESS_LABELS: Record<string, string> = {
  claude_code: 'Claude Code',
  'claude-code': 'Claude Code',
  opencode: 'OpenCode',
  token: 'Pydantic',
  subprocess: 'Subprocess',
  pydantic_ai: 'PydanticAI',
};
const HARNESS_PROVIDER: Record<string, string> = {
  claude_code: 'anthropic',
  'claude-code': 'anthropic',
};

export const harnessLabel = (backend?: string | null): string =>
  backend ? HARNESS_LABELS[backend] ?? backend : '—';

export const providerLabel = (p: { backend?: string | null; provider?: string | null }): string =>
  p.provider || (p.backend ? HARNESS_PROVIDER[p.backend] : undefined) || 'bundled';
