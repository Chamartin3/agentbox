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

  it('shows the bound profile name and backend in the card after load', async () => {
    render(wrap(<RunnerProfileSection agentId="a1" />));
    await waitFor(() => expect(screen.queryByText(/loading/)).toBeNull());
    // Card shows profile name and friendly harness label
    expect(screen.getByText('claude-fast')).not.toBeNull();
    expect(screen.getByText('Claude Code')).not.toBeNull();
    // No combobox visible by default
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('pencil opens the pick-or-create modal; "System default" clears the binding', async () => {
    m.clearAgentRunnerProfile.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(wrap(<RunnerProfileSection agentId="a1" />));
    await waitFor(() => expect(screen.queryByText(/loading/)).toBeNull());

    await user.click(screen.getByRole('button', { name: /Change runner profile/i }));
    // Modal lists profiles in a filterable table + a system-default row (async)
    expect(screen.getByRole('dialog')).not.toBeNull();
    await user.click(await screen.findByText(/System default/i));
    await waitFor(() => expect(m.clearAgentRunnerProfile).toHaveBeenCalledWith('a1'));
  });

  it('picking another profile row calls setAgentRunnerProfile', async () => {
    m.setAgentRunnerProfile.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(wrap(<RunnerProfileSection agentId="a1" />));
    await waitFor(() => expect(screen.queryByText(/loading/)).toBeNull());

    await user.click(screen.getByRole('button', { name: /Change runner profile/i }));
    await user.click(await screen.findByText(/gpt-default/i));
    await waitFor(() => expect(m.setAgentRunnerProfile).toHaveBeenCalledWith('a1', 'p1'));
  });

  it('offers a create-new-profile action in the modal', async () => {
    const user = userEvent.setup();
    render(wrap(<RunnerProfileSection agentId="a1" />));
    await waitFor(() => expect(screen.queryByText(/loading/)).toBeNull());

    await user.click(screen.getByRole('button', { name: /Change runner profile/i }));
    expect(await screen.findByRole('button', { name: /create new profile/i })).not.toBeNull();
  });
});
