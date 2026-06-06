import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('@/api/client', () => ({
  api: {
    listAgents: vi.fn(),
    getAgent: vi.fn(),
    createAgent: vi.fn(),
    patchAgent: vi.fn(),
    disableAgent: vi.fn(),
    enableAgent: vi.fn(),
    setAgentRunnerProfile: vi.fn(),
    clearAgentRunnerProfile: vi.fn(),
  },
}));

import { api } from '@/api/client';
import { useAgent, useAgentActions, useAgents } from '@/hooks/agents';

const mocked = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe('agents hooks', () => {
  beforeEach(() => {
    Object.values(mocked).forEach((m) => m.mockReset());
  });

  describe('useAgents', () => {
    it('fetches the agent list', async () => {
      mocked.listAgents.mockResolvedValue([{ id: 'a' }, { id: 'b' }]);
      const { result } = renderHook(() => useAgents());
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data).toEqual([{ id: 'a' }, { id: 'b' }]);
      expect(mocked.listAgents).toHaveBeenCalledWith({ includeDisabled: false });
    });

    it('passes includeDisabled through', async () => {
      mocked.listAgents.mockResolvedValue([]);
      renderHook(() => useAgents({ includeDisabled: true }));
      await waitFor(() =>
        expect(mocked.listAgents).toHaveBeenCalledWith({ includeDisabled: true }),
      );
    });
  });

  describe('useAgent', () => {
    it('skips fetching when id is null', async () => {
      const { result } = renderHook(() => useAgent(null));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mocked.getAgent).not.toHaveBeenCalled();
      expect(result.current.data).toBeNull();
    });

    it('loads when id provided', async () => {
      mocked.getAgent.mockResolvedValue({ agent: { id: 'x' } });
      const { result } = renderHook(() => useAgent('x'));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(mocked.getAgent).toHaveBeenCalledWith('x');
      expect(result.current.data).toEqual({ agent: { id: 'x' } });
    });
  });

  describe('useAgentActions', () => {
    it.each([
      ['create', 'createAgent', [{ id: 'a' }]],
      ['patch', 'patchAgent', ['a', { description: 'd' }]],
      ['disable', 'disableAgent', ['a']],
      ['enable', 'enableAgent', ['a']],
      ['setRunnerProfile', 'setAgentRunnerProfile', ['a', 'p1']],
      ['clearRunnerProfile', 'clearAgentRunnerProfile', ['a']],
    ] as const)('%s delegates to api.%s', async (action, apiFn, args) => {
      mocked[apiFn].mockResolvedValue('ok');
      const { result } = renderHook(() => useAgentActions());
      const fn = result.current[action] as (...a: unknown[]) => Promise<unknown>;
      await act(async () => {
        const res = await fn(...args);
        expect(res).toBe('ok');
      });
      expect(mocked[apiFn]).toHaveBeenCalledWith(...args);
    });
  });
});
