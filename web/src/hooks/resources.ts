import { useMemo } from 'react';
import {
  repoApi,
  type RepoResource,
  type RepoType,
  type RepoVersion,
} from '../api/repo';
import { useFetch } from './fetch';

export interface ResourceBundle {
  resource: RepoResource;
  activeVersion: RepoVersion | null;
  versions: RepoVersion[];
  rendered: string;
}

async function loadResourceBundle(id: string): Promise<ResourceBundle> {
  const [detail, vs] = await Promise.all([repoApi.get(id), repoApi.versions(id)]);
  let rendered = '';
  if (detail.active_version) {
    try {
      const r = await repoApi.render(id, detail.active_version.id);
      rendered = r.text || '';
    } catch {
      rendered = '';
    }
  }
  return {
    resource: detail.resource,
    activeVersion: detail.active_version,
    versions: vs.items,
    rendered,
  };
}

export function useResource(id: string | null | undefined) {
  return useFetch<ResourceBundle | null>(
    async () => (id ? await loadResourceBundle(id) : null),
    [id ?? ''],
  );
}

export function useResourceList(params: {
  type?: RepoType;
  q?: string;
  limit?: number;
  offset?: number;
} = {}) {
  const key = JSON.stringify(params);
  return useFetch(() => repoApi.list(params), [key]);
}

export function useResourceVersions(id: string | null | undefined) {
  return useFetch<RepoVersion[]>(
    async () => (id ? (await repoApi.versions(id)).items : []),
    [id ?? ''],
  );
}

export function useResourceActions() {
  // Stable wrapper over repoApi mutating + export endpoints. Pages should
  // consume this rather than importing repoApi directly so the abstraction
  // boundary stays clean.
  return useMemo(
    () => ({
      list: repoApi.list,
      create: repoApi.create,
      update: repoApi.update,
      uploadVersion: repoApi.uploadVersion,
      uploadZip: repoApi.uploadZip,
      uploadSchema: repoApi.uploadSchema,
      uploadScript: repoApi.uploadScript,
      publish: repoApi.publish,
      rollback: repoApi.rollback,
      render: repoApi.render,
      blob: repoApi.blob,
      tree: repoApi.tree,
      remove: repoApi.remove,
      versions: repoApi.versions,
      get: repoApi.get,
      exportPydantic: repoApi.exportPydantic,
      exportZipUrl: repoApi.exportZipUrl,
      validateScript: repoApi.validateScript,
    }),
    [],
  );
}
