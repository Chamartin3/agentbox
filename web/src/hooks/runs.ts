import { useCallback } from 'react';
import {
  api,
  type RunPromptDoc,
  type RunRecord,
  type RunsFacets,
  type RunsPage,
  type RunsStats,
  type UsageRecord,
} from '../api/client';
import { useFetch } from './fetch';

export type RunsQuery = Parameters<typeof api.listRunsPaged>[0];

export interface RunDetail {
  run: RunRecord;
  usage: UsageRecord | null;
}

export function useRunsPage(q: RunsQuery) {
  const key = JSON.stringify(q);
  return useFetch<RunsPage>(() => api.listRunsPaged(q), [key]);
}

export function useRunStats(q?: RunsQuery) {
  const key = JSON.stringify(q ?? null);
  return useFetch<RunsStats>(() => api.runStats(q), [key]);
}

export function useRunFacets() {
  return useFetch<RunsFacets>(() => api.runFacets(), []);
}

export function useRun(id: string | null | undefined) {
  return useFetch<RunDetail | null>(
    async () => (id ? await api.getRun(id) : null),
    [id ?? ''],
  );
}

export function useRunPrompt(id: string | null | undefined) {
  return useFetch<RunPromptDoc | null>(
    async () => (id ? await api.getRunPrompt(id) : null),
    [id ?? ''],
  );
}

export function useRunTranscript(id: string | null | undefined) {
  return useFetch<Array<Record<string, unknown>>>(
    async () => (id ? await api.getTranscript(id) : []),
    [id ?? ''],
  );
}

export function useRunComments(id: string | null | undefined) {
  return useFetch<Awaited<ReturnType<typeof api.listRunComments>> | null>(
    async () => (id ? await api.listRunComments(id) : null),
    [id ?? ''],
  );
}

export function useRunActions() {
  const cancel = useCallback((id: string) => api.cancelRun(id), []);
  const rerun = useCallback((id: string) => api.rerunRun(id), []);
  const addComment = useCallback(
    (id: string, body: string, author?: string) => api.addRunComment(id, body, author),
    [],
  );
  const fetchTranscript = useCallback((id: string) => api.getTranscript(id), []);
  return { cancel, rerun, addComment, fetchTranscript };
}
