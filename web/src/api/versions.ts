/**
 * Typed client for agent versioning API endpoints.
 * Consumed by: AgentVersions, AgentVersionDiff, CommentThread, RatingStars components.
 */

import { api } from './client';

export interface VersionSummary {
  id: string;
  version: number;
  author: string;
  changelog: string;
  is_legacy: boolean;
  is_draft: boolean;
  is_active: boolean;
  created_at: string;
}

export interface VersionListResponse {
  agent_id: string;
  latest_version: number | null;
  active_version: number | null;
  active_version_id: string | null;
  versions: VersionSummary[];
}

export interface VersionDetail {
  id: string;
  agent_id: string;
  version: number;
  author: string;
  created_at: string;
  changelog: string;
  prompt_content: string;
  agent_metadata: Record<string, unknown>;
  is_legacy: boolean;
}

export interface DiffResponse {
  from_version: number;
  to_version: number;
  prompt_diff: string;
  content_diff: Record<string, unknown>;
}

export interface Comment {
  id: string;
  version_id: string;
  author: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface CommentThreadResponse {
  version_id: string;
  comments: Comment[];
}

export interface Rating {
  version_id: string;
  rater: string;
  rating: number; // 1-5
  created_at: string;
}

export class VersionsClient {
  async listVersions(agentId: string): Promise<VersionListResponse> {
    const resp = await fetch(`/api/agents/${agentId}/versions`);
    if (!resp.ok) throw new Error(`Failed to list versions: ${resp.status}`);
    return resp.json();
  }

  async getVersion(agentId: string, versionId: string): Promise<VersionDetail> {
    const resp = await fetch(`/api/agents/${agentId}/versions/${versionId}`);
    if (!resp.ok) throw new Error(`Failed to get version: ${resp.status}`);
    return resp.json();
  }

  async diffVersions(
    agentId: string,
    fromVersion: number,
    toVersion: number
  ): Promise<DiffResponse> {
    const resp = await fetch(
      `/api/agents/${agentId}/versions/${fromVersion}/diff/${toVersion}`
    );
    if (!resp.ok) throw new Error(`Failed to diff versions: ${resp.status}`);
    return resp.json();
  }

  async activate(agentId: string, version: number): Promise<void> {
    const resp = await fetch(`/api/agents/${agentId}/versions/${version}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'activate from UI' }),
    });
    if (!resp.ok) throw new Error(`Failed to activate: ${resp.status}`);
  }

  async getComments(versionId: string): Promise<CommentThreadResponse> {
    const resp = await fetch(`/api/versions/${versionId}/comments`);
    if (!resp.ok) throw new Error(`Failed to get comments: ${resp.status}`);
    return resp.json();
  }

  async postComment(versionId: string, body: string): Promise<Comment> {
    const resp = await fetch(`/api/versions/${versionId}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body }),
    });
    if (!resp.ok) throw new Error(`Failed to post comment: ${resp.status}`);
    return resp.json();
  }

  async getRating(versionId: string): Promise<Rating | null> {
    const resp = await fetch(`/api/versions/${versionId}/rating`);
    if (resp.status === 404) return null;
    if (!resp.ok) throw new Error(`Failed to get rating: ${resp.status}`);
    return resp.json();
  }

  async setRating(versionId: string, rating: number): Promise<Rating> {
    const resp = await fetch(`/api/versions/${versionId}/rating`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    });
    if (!resp.ok) throw new Error(`Failed to set rating: ${resp.status}`);
    return resp.json();
  }

  async clearRating(versionId: string): Promise<void> {
    const resp = await fetch(`/api/versions/${versionId}/rating`, {
      method: 'DELETE',
    });
    if (!resp.ok) throw new Error(`Failed to clear rating: ${resp.status}`);
  }

  async savePromptRevision(
    agentId: string,
    promptContent: string,
    changelog: string = '',
    activate: boolean = true,
  ): Promise<VersionSummary> {
    const resp = await fetch(`/api/agents/${agentId}/versions/prompt-revision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt_content: promptContent, changelog, activate, author: 'ui' }),
    });
    if (!resp.ok) throw new Error(`Failed to save prompt revision: ${resp.status}`);
    return resp.json();
  }

  async saveNewVersion(
    agentId: string,
    content: string,
    changelog: string
  ): Promise<VersionSummary> {
    const resp = await fetch(`/api/agents/${agentId}/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, changelog }),
    });
    if (!resp.ok) throw new Error(`Failed to save version: ${resp.status}`);
    return resp.json();
  }

  async rollback(agentId: string, versionId: string): Promise<void> {
    const resp = await fetch(
      `/api/agents/${agentId}/versions/${versionId}/rollback`,
      { method: 'POST' }
    );
    if (!resp.ok) throw new Error(`Failed to rollback: ${resp.status}`);
  }
}

export const versionsApi = new VersionsClient();
