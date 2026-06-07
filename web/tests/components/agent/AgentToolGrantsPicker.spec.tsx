import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/http', () => ({ apiRequest: vi.fn() }));
import { apiRequest } from '@/api/http';
import { AgentToolGrantsPicker } from '@/components/agent/AgentToolGrantsPicker';

const req = apiRequest as unknown as ReturnType<typeof vi.fn>;

const TOOLS = {
  items: [
    { name: 'fs.read', description: 'read files', capability: 'fs', tags: [] },
    { name: 'shell.exec', description: 'run shell', capability: 'shell', tags: [] },
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

describe('AgentToolGrantsPicker', () => {
  beforeEach(mockLoad);

  it('lists active grants and ungranted tools', async () => {
    render(<AgentToolGrantsPicker agentId="a1" />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());
    expect(screen.getByText('fs.read')).not.toBeNull();
    // ungranted shell.exec appears as <option>
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toContain('shell.exec');
  });

  it('grant button stays disabled until reason is long enough', async () => {
    const user = userEvent.setup();
    render(<AgentToolGrantsPicker agentId="a1" />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());

    const select = screen.getByRole('combobox');
    await user.selectOptions(select, 'shell.exec');
    const grantBtn = screen.getByRole('button', { name: 'Grant' }) as HTMLButtonElement;
    expect(grantBtn.disabled).toBe(true);

    await user.type(screen.getByPlaceholderText(/Reason \(required/), 'ok!');
    expect(grantBtn.disabled).toBe(false);
  });

  it('POSTs a grant with tool name and reason', async () => {
    const user = userEvent.setup();
    render(<AgentToolGrantsPicker agentId="a1" />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());

    await user.selectOptions(screen.getByRole('combobox'), 'shell.exec');
    await user.type(screen.getByPlaceholderText(/Reason \(required/), 'needed');
    await user.click(screen.getByRole('button', { name: 'Grant' }));

    await waitFor(() =>
      expect(req).toHaveBeenCalledWith(
        '/api/agents/a1/tool_grants',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ tool_name: 'shell.exec', changelog: 'needed' }),
        }),
      ),
    );
  });
});
