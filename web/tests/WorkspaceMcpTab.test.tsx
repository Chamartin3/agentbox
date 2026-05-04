import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import WorkspaceMcpTab from '../src/components/WorkspaceMcpTab';

global.fetch = vi.fn();

type FetchResponse = { ok: boolean; status: number; json: () => Promise<object> };

function mockFetchSequence(responses: FetchResponse[]) {
  let callIndex = 0;
  (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(() => {
    const resp = responses[callIndex] ?? responses[responses.length - 1];
    callIndex++;
    return Promise.resolve(resp);
  });
}

function makeResp(status: number, body: object): FetchResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

describe('WorkspaceMcpTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders MCP Policy heading', async () => {
    mockFetchSequence([
      makeResp(200, { workspace_id: 'ws-1', policy: { allow_all: false, allowed_servers: ['my-mcp'] } }),
      makeResp(200, { workspace_id: 'ws-1', servers: [] }),
    ]);
    render(<WorkspaceMcpTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('MCP Policy')).not.toBeNull();
    });
  });

  it('renders MCP Server Overrides heading', async () => {
    mockFetchSequence([
      makeResp(200, { workspace_id: 'ws-1', policy: { allow_all: true } }),
      makeResp(200, { workspace_id: 'ws-1', servers: [] }),
    ]);
    render(<WorkspaceMcpTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('MCP Server Overrides')).not.toBeNull();
    });
  });

  it('displays allow_all policy', async () => {
    mockFetchSequence([
      makeResp(200, { workspace_id: 'ws-1', policy: { allow_all: true } }),
      makeResp(200, { workspace_id: 'ws-1', servers: [] }),
    ]);
    render(<WorkspaceMcpTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('yes')).not.toBeNull();
    });
  });

  it('lists allowed servers as tags', async () => {
    mockFetchSequence([
      makeResp(200, { workspace_id: 'ws-1', policy: { allow_all: false, allowed_servers: ['server-a', 'server-b'] } }),
      makeResp(200, { workspace_id: 'ws-1', servers: [] }),
    ]);
    render(<WorkspaceMcpTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('server-a')).not.toBeNull();
      expect(screen.queryByText('server-b')).not.toBeNull();
    });
  });

  it('renders server rows', async () => {
    mockFetchSequence([
      makeResp(200, { workspace_id: 'ws-1', policy: { allow_all: false } }),
      makeResp(200, {
        workspace_id: 'ws-1',
        servers: [
          { name: 'my-server', url: 'http://localhost:8080', enabled: true },
        ],
      }),
    ]);
    render(<WorkspaceMcpTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('my-server')).not.toBeNull();
      expect(screen.queryByText('http://localhost:8080')).not.toBeNull();
    });
  });

  it('shows no policy state when 404', async () => {
    mockFetchSequence([
      makeResp(404, {}),
      makeResp(404, {}),
    ]);
    render(<WorkspaceMcpTab workspaceId="ws-missing" />);
    await waitFor(() => {
      expect(screen.queryByText('No MCP policy configured.')).not.toBeNull();
      expect(screen.queryByText('No server overrides defined.')).not.toBeNull();
    });
  });

  it('shows loading state initially', () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => undefined));
    render(<WorkspaceMcpTab workspaceId="ws-1" />);
    expect(screen.queryByText('loading MCP config…')).not.toBeNull();
  });
});
