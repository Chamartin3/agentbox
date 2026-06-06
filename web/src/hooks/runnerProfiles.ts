import { useCallback } from 'react';
import { api, type RunnerBackend, type RunnerProfile, type RunnerProvider } from '../api/client';
import { useFetch } from './fetch';

export function useRunnerProfiles() {
  return useFetch<RunnerProfile[]>(() => api.listRunnerProfiles(), []);
}

export function useRunnerProviders() {
  return useFetch<RunnerProvider[]>(() => api.listRunnerProviders(), []);
}

export function useRunnerBackends() {
  return useFetch<RunnerBackend[]>(() => api.listRunnerBackends(), []);
}

export function useRunnerProfileActions(onChange: () => void | Promise<void>) {
  const refreshProviders = useCallback(async () => {
    const res = await api.refreshRunnerProviders();
    await onChange();
    return res;
  }, [onChange]);

  const remove = useCallback(
    async (id: string) => {
      await api.deleteRunnerProfile(id);
      await onChange();
    },
    [onChange],
  );

  return { refreshProviders, remove };
}
