/**
 * Typed client for agent versioning API endpoints.
 * Consumed by: AgentVersions, AgentVersionDiff, CommentThread, RatingStars components.
 */

import { apiRequest, apiRequestOrNull } from './http';

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
  agent_id?: string;
  version: number;
  author: string;
  created_at: string;
  changelog: string;
  prompt_content?: string;
  agent_metadata?: Record<string, unknown>;
  content_snapshot?: string;
  prompt_snapshot?: string;
  comments?: Comment[];
  rating?: Rating | null;
  is_legacy: boolean;
}

export interface DiffResponse {
  from_version: number;
  to_version: number;
  prompt_diff: string;
  content_diff: Record<string, unknown>;
  metadata_diff?: Array<{ key: string; from: unknown; to: unknown }>;
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
  listVersions(agentId: string): Promise<VersionListResponse> {
    return apiRequest(`/api/agents/${agentId}/versions`);
  }

  getVersion(agentId: string, versionId: string): Promise<VersionDetail> {
    return apiRequest(`/api/agents/${agentId}/versions/${versionId}`);
  }

  diffVersions(
    agentId: string,
    fromVersion: number,
    toVersion: number,
  ): Promise<DiffResponse> {
    return apiRequest(
      `/api/agents/${agentId}/versions/${fromVersion}/diff/${toVersion}`,
    );
  }

  activate(agentId: string, version: number): Promise<void> {
    return apiRequest(`/api/agents/${agentId}/versions/${version}/publish`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'activate from UI' }),
    });
  }

  getComments(versionId: string): Promise<CommentThreadResponse> {
    return apiRequest(`/api/versions/${versionId}/comments`);
  }

  postComment(versionId: string, body: string): Promise<Comment> {
    return apiRequest(`/api/versions/${versionId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ body }),
    });
  }

  getRating(versionId: string): Promise<Rating | null> {
    return apiRequestOrNull<Rating>(`/api/versions/${versionId}/rating`);
  }

  setRating(versionId: string, rating: number): Promise<Rating> {
    return apiRequest(`/api/versions/${versionId}/rating`, {
      method: 'POST',
      body: JSON.stringify({ rating }),
    });
  }

  clearRating(versionId: string): Promise<void> {
    return apiRequest(`/api/versions/${versionId}/rating`, { method: 'DELETE' });
  }

  savePromptRevision(
    agentId: string,
    promptContent: string,
    changelog: string = '',
    activate: boolean = true,
  ): Promise<VersionSummary> {
    return apiRequest(`/api/agents/${agentId}/versions/prompt-revision`, {
      method: 'POST',
      body: JSON.stringify({
        prompt_content: promptContent,
        changelog,
        activate,
        author: 'ui',
      }),
    });
  }

  saveNewVersion(
    agentId: string,
    content: string,
    changelog: string,
  ): Promise<VersionSummary> {
    return apiRequest(`/api/agents/${agentId}/versions`, {
      method: 'POST',
      body: JSON.stringify({ content, changelog }),
    });
  }

  rollback(agentId: string, versionId: string): Promise<void> {
    return apiRequest(
      `/api/agents/${agentId}/versions/${versionId}/rollback`,
      { method: 'POST' },
    );
  }
}

export const versionsApi = new VersionsClient();
