import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/http', () => ({ apiRequest: vi.fn() }));
import { apiRequest } from '@/api/http';
import { AgentToolGrantsPicker } from '@/components/agent/AgentToolGrantsPicker';

const req = apiRequest as unknown as ReturnType<typeof vi.fn>;

const TOOLS = {
  items: [
    { name: 'fs.read', description: 'read files', kind: 'builtin' },
    { name: 'shell.exec', description: 'run shell', kind: 'builtin' },
  ],
};
const GRANTS = {
  items: [
    {
      tool_name: 'fs.read',
      granted_at: '2026-01-01T00:00:00Z',
      granted_by: 'alice',
      changelog: 'because',
    },
  ],
};

const mockLoad = () => {
  req.mockReset();
  req.mockImplementation((path: string) => {
    if (path === '/api/agent_tools') return Promise.resolve(TOOLS);
    if (path.endsWith('/tool_grants')) return Promise.resolve(GRANTS);
    return Promise.resolve({});
  });
};

const box = (short: string) =>
  screen.getByText(short).closest('label')!.querySelector('input') as HTMLInputElement;

describe('AgentToolGrantsPicker', () => {
  beforeEach(mockLoad);

  it('renders a checkbox per tool with the granted one enabled and a live count', async () => {
    render(<AgentToolGrantsPicker agentId="a1" workspaceId={null} />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());

    // Short names shown; granted count reflected
    expect(screen.getByText('read')).not.toBeNull();
    expect(screen.getByText('exec')).not.toBeNull();
    expect(screen.getByText('1 enabled')).not.toBeNull();

    expect(box('read').checked).toBe(true);   // fs.read granted
    expect(box('exec').checked).toBe(false);  // shell.exec ungranted
  });

  it('toggling a tool reveals the apply bar, disabled until reason is long enough', async () => {
    const user = userEvent.setup();
    render(<AgentToolGrantsPicker agentId="a1" workspaceId={null} />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());

    await user.click(box('exec'));
    const applyBtn = screen.getByRole('button', { name: /apply 1 change/i }) as HTMLButtonElement;
    expect(applyBtn.disabled).toBe(true);

    await user.type(screen.getByPlaceholderText(/reason \(required/i), 'ok!');
    expect(applyBtn.disabled).toBe(false);
  });

  it('applies pending grants and revokes with one shared reason', async () => {
    const user = userEvent.setup();
    render(<AgentToolGrantsPicker agentId="a1" workspaceId={null} />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());

    await user.click(box('exec'));   // grant shell.exec
    await user.click(box('read'));   // revoke fs.read
    await user.type(screen.getByPlaceholderText(/reason \(required/i), 'needed');
    await user.click(screen.getByRole('button', { name: /apply 2 changes/i }));

    await waitFor(() =>
      expect(req).toHaveBeenCalledWith(
        '/api/agents/a1/tool_grants',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ tool_name: 'shell.exec', changelog: 'needed', workspace_id: null }),
        }),
      ),
    );
    expect(req).toHaveBeenCalledWith(
      '/api/agents/a1/tool_grants/fs.read',
      expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({ changelog: 'needed' }),
      }),
    );
  });
});
