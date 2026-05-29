// Wire-format event types mirroring backend src/agentbox/api/events.py.
// Single source of truth for the WS stream + transcript shape.

export const EVENT_TYPES = [
  'text',
  'log',
  'tool_call',
  'tool_result',
  'usage',
  'retry',
  'thinking',
  'timeout',
  'validation',
  'done',
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

interface EventBase {
  ts?: string;
  run_id?: string;
}

export interface TextEvent extends EventBase {
  type: 'text';
  text: string;
  role?: 'assistant' | 'user' | 'system';
  delta?: boolean;
}

export interface LogEvent extends EventBase {
  type: 'log';
  level?: 'debug' | 'info' | 'warn' | 'error';
  message: string;
}

export interface ToolCallEvent extends EventBase {
  type: 'tool_call';
  tool: string;
  arguments: Record<string, unknown>;
  call_id?: string | null;
}

export interface ToolResultEvent extends EventBase {
  type: 'tool_result';
  tool: string;
  call_id?: string | null;
  ok?: boolean;
  result_excerpt?: string | null;
}

export interface UsageEvent extends EventBase {
  type: 'usage';
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  cost_usd?: number | null;
  model?: string | null;
}

export interface RetryEvent extends EventBase {
  type: 'retry';
  attempt?: number;
  reason?: string;
  error?: string | null;
}

export interface ThinkingEvent extends EventBase {
  type: 'thinking';
  text: string;
}

export interface TimeoutEvent extends EventBase {
  type: 'timeout';
  timeout_seconds?: number;
  error?: string | null;
}

export interface ValidationEvent extends EventBase {
  type: 'validation';
  ok: boolean;
  attempt?: number;
  mode?: 'strict' | 'warn' | 'off';
  engine?: 'jsonschema' | 'pydantic' | 'both' | 'none';
  error?: string | null;
}

export interface DoneEvent extends EventBase {
  type: 'done';
  ok: boolean;
  exit_code?: number | null;
  error?: string | null;
  status?: 'ok' | 'error' | 'timeout' | null;
}

export type RunEvent =
  | TextEvent
  | LogEvent
  | ToolCallEvent
  | ToolResultEvent
  | UsageEvent
  | RetryEvent
  | ThinkingEvent
  | TimeoutEvent
  | ValidationEvent
  | DoneEvent;

// UI extension flags added in-memory by the event-stream coalescer.
// Not part of the wire format — kept here so consumers don't redeclare them.
export interface CoalescedFlags {
  _coalesced?: boolean;
  _coalesced_count?: number;
}

export type UiRunEvent = RunEvent & CoalescedFlags;

// Loose shape for UI code that indexes arbitrary fields without
// narrowing on `type`. Prefer `RunEvent` when you can.
export interface LooseStreamEvent extends CoalescedFlags {
  type: string;
  [k: string]: unknown;
}

// Visual metadata for each event type. Centralized so EventStream,
// ConversationView, and any future viewer share the same palette.
export interface EventMeta {
  label: string;
  color: string;
  bg: string;
}

export const EVENT_META: Record<EventType, EventMeta> = {
  text:        { label: 'text',       color: '#c9d1d9', bg: 'rgba(201,209,217,0.08)' },
  log:         { label: 'log',        color: '#8b949e', bg: 'rgba(139,148,158,0.08)' },
  tool_call:   { label: 'call',       color: '#79c0ff', bg: 'rgba(121,192,255,0.10)' },
  tool_result: { label: 'result',     color: '#3fb950', bg: 'rgba(63,185,80,0.10)' },
  usage:       { label: 'usage',      color: '#d29922', bg: 'rgba(210,153,34,0.10)' },
  retry:       { label: 'retry',      color: '#f0883e', bg: 'rgba(240,136,62,0.10)' },
  thinking:    { label: 'thinking',   color: '#58a6ff', bg: 'rgba(88,166,255,0.10)' },
  timeout:     { label: 'timeout',    color: '#f0883e', bg: 'rgba(240,136,62,0.15)' },
  validation:  { label: 'validation', color: '#d2a8ff', bg: 'rgba(210,168,255,0.10)' },
  done:        { label: 'done',       color: '#58a6ff', bg: 'rgba(88,166,255,0.10)' },
};

const UNKNOWN_META: EventMeta = {
  label: 'unknown',
  color: 'var(--fg-muted)',
  bg: 'rgba(139,148,158,0.06)',
};

export function getEventMeta(type: string): EventMeta {
  return (EVENT_META as Record<string, EventMeta>)[type] ?? { ...UNKNOWN_META, label: type };
}

// One-line summary of an event, used in compact list rows.
export function summarizeEvent(ev: LooseStreamEvent): string {
  switch (ev.type) {
    case 'text':
      return String(ev.text ?? '').slice(0, 180);
    case 'log':
      return `[${ev.level ?? ''}] ${String(ev.message ?? '').slice(0, 180)}`;
    case 'tool_call':
      return `${ev.tool ?? ''} ${JSON.stringify(ev.arguments ?? {}).slice(0, 140)}`;
    case 'tool_result':
      return `${ev.tool ?? ''} ok=${ev.ok}`;
    case 'usage':
      return `in=${ev.input_tokens ?? 0} out=${ev.output_tokens ?? 0} cost=$${ev.cost_usd ?? 0}`;
    case 'done':
      return `status=${ev.status ?? ''}`;
    case 'retry':
      return `attempt=${ev.attempt ?? ''} reason=${ev.reason ?? ''}`;
    case 'thinking':
      return String(ev.text ?? '').slice(0, 180);
    case 'timeout':
      return `timeout after ${ev.timeout_seconds ?? '?'}s`;
    case 'validation':
      return `ok=${ev.ok} engine=${ev.engine ?? ''} mode=${ev.mode ?? ''} attempt=${ev.attempt ?? ''}${ev.error ? ` — ${String(ev.error).slice(0, 120)}` : ''}`;
    default:
      return JSON.stringify(ev).slice(0, 180);
  }
}
