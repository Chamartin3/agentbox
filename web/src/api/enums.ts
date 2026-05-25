// Centralised enums to avoid magic strings across the UI.
// Use `as const` objects so values stay plain strings on the wire
// while consumers get autocomplete + exhaustiveness.

export const SortDir = { Asc: 'asc', Desc: 'desc' } as const;
export type SortDir = (typeof SortDir)[keyof typeof SortDir];

export const AgentSortKey = {
  Id: 'id',
  Runner: 'runner',
  Model: 'model',
  UpdatedAt: 'updated_at',
  LastRun: 'last_run',
} as const;
export type AgentSortKey = (typeof AgentSortKey)[keyof typeof AgentSortKey];

export const RunsFilterKey = {
  Agent: 'agent',
  Status: 'status',
  Executor: 'executor',
  Q: 'q',
  Page: 'page',
} as const;
export type RunsFilterKey = (typeof RunsFilterKey)[keyof typeof RunsFilterKey];

export const BackendId = {
  Token: 'token',
  ClaudeCode: 'claude_code',
  OpenCode: 'opencode',
  Codex: 'codex',
  Pi: 'pi',
} as const;
export type BackendId = (typeof BackendId)[keyof typeof BackendId];

export const RepoType = {
  Document: 'document',
  Folder: 'folder',
  Skill: 'skill',
  Schema: 'schema',
  Script: 'script',
} as const;
export type RepoType = (typeof RepoType)[keyof typeof RepoType];

export const ResourceKind = {
  OutputSchema: 'output_schema',
  InputSchema: 'input_schema',
  UserTemplate: 'user_template',
  SystemFragment: 'system_fragment',
  Reference: 'reference',
  McpServer: 'mcp_server',
  Skill: 'skill',
} as const;
export type ResourceKind = (typeof ResourceKind)[keyof typeof ResourceKind];

export const MaterializeMode = {
  Copy: 'copy',
  Symlink: 'symlink',
  Mount: 'mount',
} as const;
export type MaterializeMode = (typeof MaterializeMode)[keyof typeof MaterializeMode];

export const ConflictPolicy = {
  Error: 'error',
  Overwrite: 'overwrite',
  Skip: 'skip',
} as const;
export type ConflictPolicy = (typeof ConflictPolicy)[keyof typeof ConflictPolicy];

export const McpDefaultPolicy = {
  Allow: 'allow',
  Deny: 'deny',
} as const;
export type McpDefaultPolicy = (typeof McpDefaultPolicy)[keyof typeof McpDefaultPolicy];

// Single source of truth lives in theme/statusColors.ts (where the
// status palette and canonicalStatus mapper also live). Re-exported
// here so api/enums stays the one-stop import for UI enums.
export { RunStatus } from '../theme/statusColors';

export const ToastKind = { Ok: 'ok', Error: 'error' } as const;
export type ToastKind = (typeof ToastKind)[keyof typeof ToastKind];

export const PromptMode = {
  Inline: 'inline',
  SkillPrimer: 'skill_primer',
  NameOnly: 'name_only',
  Manifest: 'manifest',
} as const;
export type PromptMode = (typeof PromptMode)[keyof typeof PromptMode];
