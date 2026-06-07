import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return {
    ...actual,
    api: {
      getAgentRunnerProfile: vi.fn(),
      listRunnerProfiles: vi.fn(),
      listRunnerProviders: vi.fn(),
      listRunnerBackends: vi.fn(),
      setAgentRunnerProfile: vi.fn(),
      clearAgentRunnerProfile: vi.fn(),
    },
  };
});
vi.mock('@/api/api_tokens', () => ({
  apiTokens: { listSafe: vi.fn() },
}));
// Modal pulls in a lot; we only smoke-test the section itself.
vi.mock('@/components/runner/RunnerProfileModal', () => ({
  default: () => <div data-testid="modal" />,
}));

import { api } from '@/api/client';
import { apiTokens } from '@/api/api_tokens';
import { RunnerProfileSection } from '@/components/runner/RunnerProfileSection';

const m = api as unknown as Record<string, ReturnType<typeof vi.fn>>;
const tok = apiTokens as unknown as Record<string, ReturnType<typeof vi.fn>>;

const PROFILES = [
  { id: 'p1', name: 'gpt-default', backend: 'token', provider: 'openai', model: 'gpt-5', is_system_default: true },
  { id: 'p2', name: 'claude-fast', backend: 'claude-code', provider: null, model: null, is_system_default: false },
];

const wrap = (ui: React.ReactNode) => <MemoryRouter>{ui}</MemoryRouter>;

describe('RunnerProfileSection', () => {
  beforeEach(() => {
    Object.values(m).forEach((fn) => fn.mockReset());
    tok.listSafe.mockReset();
    m.getAgentRunnerProfile.mockResolvedValue(PROFILES[1]);
    m.listRunnerProfiles.mockResolvedValue(PROFILES);
    m.listRunnerProviders.mockResolvedValue([]);
    m.listRunnerBackends.mockResolvedValue([]);
    tok.listSafe.mockResolvedValue([]);
  });

  it('shows the bound profile in the select after load', async () => {
    render(wrap(<RunnerProfileSection agentId="a1" />));
    await waitFor(() => expect(screen.queryByText(/loading/)).toBeNull());
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('p2');
    expect(screen.getByText(/bound to/)).not.toBeNull();
  });

  it('changing to "" clears the bound profile', async () => {
    m.clearAgentRunnerProfile.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(wrap(<RunnerProfileSection agentId="a1" />));
    await waitFor(() => expect(screen.queryByText(/loading/)).toBeNull());

    await user.selectOptions(screen.getByRole('combobox'), '');
    await waitFor(() => expect(m.clearAgentRunnerProfile).toHaveBeenCalledWith('a1'));
  });

  it('changing to another profile calls setAgentRunnerProfile', async () => {
    m.setAgentRunnerProfile.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(wrap(<RunnerProfileSection agentId="a1" />));
    await waitFor(() => expect(screen.queryByText(/loading/)).toBeNull());

    await user.selectOptions(screen.getByRole('combobox'), 'p1');
    await waitFor(() => expect(m.setAgentRunnerProfile).toHaveBeenCalledWith('a1', 'p1'));
  });
});
