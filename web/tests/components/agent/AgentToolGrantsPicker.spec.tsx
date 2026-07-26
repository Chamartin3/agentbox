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

// Catalog with MCP-server items and host_env items mixed in
const TOOLS_WITH_MCP = {
  items: [
    { name: 'fs.read', description: 'read files', kind: 'builtin' },
    { name: 'shell.exec', description: 'run shell', kind: 'builtin' },
    { name: 'mcp_tool.search', description: 'mcp search', kind: 'mcp', server: 'my_mcp_server' },
    { name: 'host_env.list', description: 'host env list', kind: 'host_env' },
  ],
};

const EMPTY_GRANTS = { items: [] };

// Backend descriptors
const NATIVE_ONLY_BACKEND = {
  id: 'pi',
  label: 'PI',
  default_model: null,
  compatible_providers: [],
  accepts_no_provider: true,
  supports_mcp: false,
  native_tools: ['fs.read', 'shell.exec'],
};

const MCP_CAPABLE_BACKEND = {
  id: 'claude-code',
  label: 'Claude Code',
  default_model: null,
  compatible_providers: ['anthropic'],
  accepts_no_provider: false,
  supports_mcp: true,
  native_tools: [],
};

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

  it('native-only harness: hides mcp and host_env items and shows native-only notice', async () => {
    req.mockReset();
    req.mockImplementation((path: string) => {
      if (path === '/api/agent_tools') return Promise.resolve(TOOLS_WITH_MCP);
      if (path.endsWith('/tool_grants')) return Promise.resolve(EMPTY_GRANTS);
      if (path === '/api/runner-backends') return Promise.resolve([NATIVE_ONLY_BACKEND]);
      return Promise.resolve({});
    });

    render(<AgentToolGrantsPicker agentId="a1" workspaceId={null} harnessBackendId="pi" />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());
    // Wait for the backend descriptor to load (second effect)
    await waitFor(() =>
      expect(screen.queryByText(/runs native tools only/i)).not.toBeNull(),
    );

    // Native tools should be visible
    expect(screen.queryByText('read')).not.toBeNull();   // fs.read → "read"
    expect(screen.queryByText('exec')).not.toBeNull();   // shell.exec → "exec"

    // MCP-server item must not be rendered
    expect(screen.queryByText('search')).toBeNull();     // mcp_tool.search → "search"

    // host_env item must not be rendered
    expect(screen.queryByText('list')).toBeNull();       // host_env.list → "list"

    // Native-only notice
    expect(screen.getByText(/runs native tools only/i)).not.toBeNull();
  });

  it('MCP-capable harness: renders mcp and host_env items, no native-only notice', async () => {
    req.mockReset();
    req.mockImplementation((path: string) => {
      if (path === '/api/agent_tools') return Promise.resolve(TOOLS_WITH_MCP);
      if (path.endsWith('/tool_grants')) return Promise.resolve(EMPTY_GRANTS);
      if (path === '/api/runner-backends') return Promise.resolve([MCP_CAPABLE_BACKEND]);
      return Promise.resolve({});
    });

    render(
      <AgentToolGrantsPicker agentId="a1" workspaceId={null} harnessBackendId="claude-code" />,
    );
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());

    // All catalog items visible
    expect(screen.queryByText('read')).not.toBeNull();
    expect(screen.queryByText('exec')).not.toBeNull();
    expect(screen.queryByText('search')).not.toBeNull();  // mcp item
    expect(screen.queryByText('list')).not.toBeNull();    // host_env item

    // No native-only notice
    expect(screen.queryByText(/runs native tools only/i)).toBeNull();
  });
});
