import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('@/api/client', () => ({
  api: {
    listRunsPaged: vi.fn(),
    runStats: vi.fn(),
    runFacets: vi.fn(),
    getRun: vi.fn(),
    getRunPrompt: vi.fn(),
    getTranscript: vi.fn(),
    listRunComments: vi.fn(),
    addRunComment: vi.fn(),
    cancelRun: vi.fn(),
    rerunRun: vi.fn(),
  },
}));

import { api } from '@/api/client';
import {
  useRun,
  useRunActions,
  useRunComments,
  useRunFacets,
  useRunPrompt,
  useRunStats,
  useRunsPage,
  useRunTranscript,
} from '@/hooks/runs';

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe('runs hooks', () => {
  beforeEach(() => {
    Object.values(mocked).forEach((m) => m.mockReset());
  });

  describe.each([
    ['useRunsPage', useRunsPage, 'listRunsPaged', [{ limit: 10 }] as const, { items: [], total: 0 }],
    ['useRunStats', useRunStats, 'runStats', [undefined] as const, { totals: {} }],
    ['useRunFacets', useRunFacets, 'runFacets', [] as const, { agents: [] }],
  ])('%s', (_name, hook, apiFn, args, payload) => {
    it('passes args through and exposes data', async () => {
      mocked[apiFn].mockResolvedValue(payload);
      const { result } = renderHook(() => hook(...(args as [never])));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data).toEqual(payload);
    });
  });

  describe.each([
    ['useRun', useRun, 'getRun'],
    ['useRunPrompt', useRunPrompt, 'getRunPrompt'],
    ['useRunComments', useRunComments, 'listRunComments'],
  ] as const)('%s with nullable id', (_n, hook, apiFn) => {
    it('skips when id is null', async () => {
      const { result } = renderHook(() => hook(null));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mocked[apiFn]).not.toHaveBeenCalled();
      expect(result.current.data).toBeNull();
    });

    it('calls when id given', async () => {
      mocked[apiFn].mockResolvedValue({ id: 'r1' });
      renderHook(() => hook('r1'));
      await waitFor(() => expect(mocked[apiFn]).toHaveBeenCalledWith('r1'));
    });
  });

  describe('useRunTranscript', () => {
    it('returns [] when id absent', async () => {
      const { result } = renderHook(() => useRunTranscript(null));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data).toEqual([]);
      expect(mocked.getTranscript).not.toHaveBeenCalled();
    });

    it('fetches when id given', async () => {
      mocked.getTranscript.mockResolvedValue([{ type: 'msg' }]);
      const { result } = renderHook(() => useRunTranscript('r1'));
      await waitFor(() => expect(result.current.data).toEqual([{ type: 'msg' }]));
    });
  });

  describe('useRunActions', () => {
    it.each([
      ['cancel', 'cancelRun', ['r1']],
      ['rerun', 'rerunRun', ['r1']],
      ['fetchTranscript', 'getTranscript', ['r1']],
    ] as const)('%s delegates to api.%s', async (action, apiFn, args) => {
      mocked[apiFn].mockResolvedValue('ok');
      const { result } = renderHook(() => useRunActions());
      await act(async () => {
        const fn = result.current[action] as (...a: unknown[]) => Promise<unknown>;
        await fn(...args);
      });
      expect(mocked[apiFn]).toHaveBeenCalledWith(...args);
    });

    it('addComment forwards body + author', async () => {
      mocked.addRunComment.mockResolvedValue({ id: 1 });
      const { result } = renderHook(() => useRunActions());
      await act(async () => {
        await result.current.addComment('r1', 'hello', 'alice');
      });
      expect(mocked.addRunComment).toHaveBeenCalledWith('r1', 'hello', 'alice');
    });
  });
});
