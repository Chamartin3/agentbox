import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import HostEnvTab from '../src/components/HostEnvTab';

global.fetch = vi.fn();

function mockFetch(status: number, body: object | null) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

const SAMPLE_GRANTS = [
  { name: 'OPENAI_API_KEY', value: 'sk-...', source: 'env', masked: true },
  { name: 'PROJECT_ROOT', value: '/workspace', source: 'config', masked: false },
];

describe('HostEnvTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders section heading', async () => {
    mockFetch(200, { workspace_id: 'ws-1', grants: SAMPLE_GRANTS });
    render(<HostEnvTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('Host Environment Grants')).not.toBeNull();
    });
  });

  it('lists grant names', async () => {
    mockFetch(200, { workspace_id: 'ws-1', grants: SAMPLE_GRANTS });
    render(<HostEnvTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('OPENAI_API_KEY')).not.toBeNull();
      expect(screen.queryByText('PROJECT_ROOT')).not.toBeNull();
    });
  });

  it('masks sensitive values', async () => {
    mockFetch(200, { workspace_id: 'ws-1', grants: SAMPLE_GRANTS });
    render(<HostEnvTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('••••••')).not.toBeNull();
    });
  });

  it('shows plain value when not masked', async () => {
    mockFetch(200, { workspace_id: 'ws-1', grants: SAMPLE_GRANTS });
    render(<HostEnvTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('/workspace')).not.toBeNull();
    });
  });

  it('shows source column', async () => {
    mockFetch(200, { workspace_id: 'ws-1', grants: SAMPLE_GRANTS });
    render(<HostEnvTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('env')).not.toBeNull();
      expect(screen.queryByText('config')).not.toBeNull();
    });
  });

  it('shows empty state when no grants', async () => {
    mockFetch(200, { workspace_id: 'ws-1', grants: [] });
    render(<HostEnvTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('No host-env grants configured for this workspace.')).not.toBeNull();
    });
  });

  it('shows empty state on 404', async () => {
    mockFetch(404, null);
    render(<HostEnvTab workspaceId="missing-ws" />);
    await waitFor(() => {
      expect(screen.queryByText('No host-env grants configured for this workspace.')).not.toBeNull();
    });
  });

  it('shows loading state initially', () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => undefined));
    render(<HostEnvTab workspaceId="ws-1" />);
    expect(screen.queryByText('loading host-env grants…')).not.toBeNull();
  });

  it('renders table headers', async () => {
    mockFetch(200, { workspace_id: 'ws-1', grants: SAMPLE_GRANTS });
    render(<HostEnvTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('Name')).not.toBeNull();
      expect(screen.queryByText('Value')).not.toBeNull();
      expect(screen.queryByText('Source')).not.toBeNull();
    });
  });
});
