import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/client', () => ({ api: { listAgents: vi.fn() } }));
vi.mock('@/api/repo', () => ({ subagentsApi: { list: vi.fn(), replace: vi.fn() } }));

import { api } from '@/api/client';
import { subagentsApi } from '@/api/repo';
import SubagentsEditor from '@/components/workspace/SubagentsEditor';

const listAgents = api.listAgents as unknown as ReturnType<typeof vi.fn>;
const list = subagentsApi.list as unknown as ReturnType<typeof vi.fn>;
const replace = subagentsApi.replace as unknown as ReturnType<typeof vi.fn>;

// The component reads only `.id` off AgentDef; a partial object is enough.
const agent = (id: string) => ({ id }) as never;

describe('SubagentsEditor', () => {
  beforeEach(() => {
    listAgents.mockReset();
    list.mockReset();
    replace.mockReset();
  });

  it('renders the bound subagents once both lists resolve', async () => {
    listAgents.mockResolvedValueOnce([agent('agent-a'), agent('agent-b')]);
    list.mockResolvedValueOnce({
      items: [{ agent_id: 'agent-a', alias: 'reviewer', display_order: 0 }],
    });

    render(<SubagentsEditor workspaceId="ws1" />);

    expect(await screen.findByText('agent-a')).toBeTruthy();
    expect(screen.getByText(/Subagents \(1\)/)).toBeTruthy();
    const alias = screen.getByDisplayValue('reviewer') as HTMLInputElement;
    expect(alias.value).toBe('reviewer');
    expect(list).toHaveBeenCalledWith('ws1');
    expect(listAgents).toHaveBeenCalled();
  });

  it('adds an available agent and Save PUTs it via subagentsApi.replace', async () => {
    // Persistent: save() calls load() again, which re-fetches the agent list.
    listAgents.mockResolvedValue([agent('agent-a'), agent('agent-b')]);
    list.mockResolvedValueOnce({ items: [] });
    const user = userEvent.setup();

    render(<SubagentsEditor workspaceId="ws1" />);
    await screen.findByText(/Subagents \(0\)/);

    await user.selectOptions(screen.getByRole('combobox'), 'agent-a');
    await user.click(screen.getByRole('button', { name: 'add' }));
    // The picked agent now shows as a local (unsaved) row.
    expect(screen.getByText(/Subagents \(1\)/)).toBeTruthy();

    replace.mockResolvedValueOnce({ items: [] });
    list.mockResolvedValueOnce({
      items: [{ agent_id: 'agent-a', alias: 'agent-a', display_order: 0 }],
    });
    await user.click(screen.getByRole('button', { name: /save subagents/i }));

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith('ws1', [
        { agent_id: 'agent-a', alias: 'agent-a', display_order: 0 },
      ]),
    );
  });

  it('shows the empty state when no subagents are assigned', async () => {
    listAgents.mockResolvedValueOnce([]);
    list.mockResolvedValueOnce({ items: [] });

    render(<SubagentsEditor workspaceId="ws1" />);

    expect(await screen.findByText('No subagents assigned.')).toBeTruthy();
    expect(screen.getByText(/Subagents \(0\)/)).toBeTruthy();
  });
});
