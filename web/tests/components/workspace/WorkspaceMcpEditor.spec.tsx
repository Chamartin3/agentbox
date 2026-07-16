import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/repo', () => ({
  workspaceMcpApi: {
    get: vi.fn(),
    setPolicy: vi.fn(),
    setServer: vi.fn(),
    setTool: vi.fn(),
    refresh: vi.fn(),
  },
}));

import { workspaceMcpApi } from '@/api/repo';
import WorkspaceMcpEditor from '@/components/workspace/WorkspaceMcpEditor';

const get = workspaceMcpApi.get as unknown as ReturnType<typeof vi.fn>;
const setServer = workspaceMcpApi.setServer as unknown as ReturnType<typeof vi.fn>;
const setTool = workspaceMcpApi.setTool as unknown as ReturnType<typeof vi.fn>;

const server = (over: Partial<Record<string, unknown>> = {}) => ({
  name: 'ctx7',
  enabled: true,
  source: 'default',
  disabled_tools: [] as string[],
  config: { tools: ['search', 'fetch'] },
  ...over,
});

describe('WorkspaceMcpEditor', () => {
  beforeEach(() => {
    get.mockReset();
    setServer.mockReset();
    setTool.mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  it('renders the effective servers and default policy', async () => {
    get.mockResolvedValueOnce({
      policy: 'allow_all_unless_disabled',
      servers: [server()],
    });

    render(<WorkspaceMcpEditor workspaceId="ws1" />);

    expect(await screen.findByText('ctx7')).toBeTruthy();
    expect(get).toHaveBeenCalledWith('ws1');
    const radios = screen.getAllByRole('radio') as HTMLInputElement[];
    expect(radios[0].checked).toBe(true); // show all servers
    expect(radios[1].checked).toBe(false);
    expect(screen.getByRole('button', { name: 'shown' })).toBeTruthy();
  });

  it('toggling a hidden server calls setServer with the flipped state', async () => {
    get.mockResolvedValue({
      policy: 'allow_all_unless_disabled',
      servers: [server({ enabled: false })],
    });
    setServer.mockResolvedValueOnce(undefined);
    vi.spyOn(window, 'prompt').mockReturnValue('showing it here');
    const user = userEvent.setup();

    render(<WorkspaceMcpEditor workspaceId="ws1" />);
    await user.click(await screen.findByRole('button', { name: 'hidden' }));

    await waitFor(() =>
      expect(setServer).toHaveBeenCalledWith('ws1', 'ctx7', true, 'showing it here'),
    );
  });

  it('toggling a tool calls setTool with the server + tool name', async () => {
    get.mockResolvedValue({
      policy: 'allow_all_unless_disabled',
      servers: [server()],
    });
    setTool.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();

    render(<WorkspaceMcpEditor workspaceId="ws1" />);
    // Expand the per-server tool list, then toggle one tool.
    await user.click(await screen.findByRole('button', { name: /tools \(2\)/ }));
    await user.click(screen.getByRole('button', { name: 'search' }));

    await waitFor(() =>
      expect(setTool).toHaveBeenCalledWith('ws1', 'ctx7', 'search', false),
    );
  });
});
