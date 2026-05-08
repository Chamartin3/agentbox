// Single source of truth for run statuses and their theme.
//
// Anything that needs to refer to a run status (chart series, pill
// classes, table filters, color lookups) imports `RunStatus` from here
// instead of using a magic string literal.
//
// Palette intent:
//   - `FAILED` is the only saturated red.
//   - `ERROR` sits in the warm family (orange) — visually close to
//     failed but distinct, since "error" and "failed" mean different
//     things.
//   - `RUNNING` is the cool/in-flight color and is intentionally
//     excluded from the activity chart because it's a transient state
//     that inflates the stack without representing completed work.

export const RunStatus = {
  OK: 'ok',
  RUNNING: 'running',
  ERROR: 'error',
  FAILED: 'failed',
  TIMEOUT: 'timeout',
  INCOMPLETE: 'incomplete',
} as const;

export type RunStatus = (typeof RunStatus)[keyof typeof RunStatus];

// Vibrant tones used for the activity chart (areas/strokes).
export const STATUS_COLORS: Record<RunStatus, string> = {
  [RunStatus.OK]: '#3fb950',
  [RunStatus.RUNNING]: '#58a6ff',
  [RunStatus.ERROR]: '#f0883e',
  [RunStatus.FAILED]: '#f85149',
  [RunStatus.TIMEOUT]: '#d29922',
  [RunStatus.INCOMPLETE]: '#8b949e',
};

// Darker tones used as pill/badge backgrounds so white text remains
// readable. Same hue family as STATUS_COLORS, just shifted toward the
// dark end of the ramp.
export const STATUS_PILL_BG: Record<RunStatus, string> = {
  [RunStatus.OK]: '#1a7f3a',
  [RunStatus.RUNNING]: '#1f4ea8',
  [RunStatus.ERROR]: '#a04a14',
  [RunStatus.FAILED]: '#9b2222',
  [RunStatus.TIMEOUT]: '#8a5a14',
  [RunStatus.INCOMPLETE]: '#4a525c',
};

// Statuses shown in the stacked-area chart. `RUNNING` is excluded
// because it's transient.
export const CHART_STATUSES: RunStatus[] = [
  RunStatus.OK,
  RunStatus.ERROR,
  RunStatus.FAILED,
  RunStatus.TIMEOUT,
  RunStatus.INCOMPLETE,
];

export function statusColor(s: string): string {
  return STATUS_COLORS[s as RunStatus] ?? '#8b949e';
}

// Map any incoming status string (including legacy aliases like
// `succeeded` and `stopped`) to a canonical RunStatus for theming.
export function canonicalStatus(s: string): RunStatus {
  if (s === 'succeeded') return RunStatus.OK;
  if (s === 'stopped') return RunStatus.INCOMPLETE;
  if ((Object.values(RunStatus) as string[]).includes(s)) return s as RunStatus;
  return RunStatus.ERROR;
}

export function installStatusCssVars(root: HTMLElement = document.documentElement) {
  for (const s of Object.values(RunStatus)) {
    root.style.setProperty(`--status-${s}`, STATUS_COLORS[s]);
    root.style.setProperty(`--status-${s}-bg`, STATUS_PILL_BG[s]);
  }
}
