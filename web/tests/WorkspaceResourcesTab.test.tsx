import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import WorkspaceResourcesTab from '../src/components/WorkspaceResourcesTab';

global.fetch = vi.fn();

function mockFetch(status: number, body: object) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

const SAMPLE_BINDINGS = [
  {
    path: '.agentbox/schemas/output.json',
    resource_id: 'output-schema',
    resource_version: 1,
    kind: 'output_schema',
    sha256: 'deadbeef00112233',
  },
  {
    path: '.agentbox/skills/my-skill.md',
    resource_id: 'my-skill',
    resource_version: null,
    kind: 'skill',
    sha256: null,
  },
];

describe('WorkspaceResourcesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders section heading', async () => {
    mockFetch(200, { workspace_id: 'ws-1', bindings: SAMPLE_BINDINGS });
    render(<WorkspaceResourcesTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('Workspace File Bindings')).not.toBeNull();
    });
  });

  it('shows empty state', async () => {
    mockFetch(200, { workspace_id: 'ws-1', bindings: [] });
    render(<WorkspaceResourcesTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('No resource file bindings for this workspace.')).not.toBeNull();
    });
  });

  it('renders binding rows', async () => {
    mockFetch(200, { workspace_id: 'ws-1', bindings: SAMPLE_BINDINGS });
    render(<WorkspaceResourcesTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('.agentbox/schemas/output.json')).not.toBeNull();
      expect(screen.queryByText('output-schema')).not.toBeNull();
      expect(screen.queryByText('.agentbox/skills/my-skill.md')).not.toBeNull();
    });
  });

  it('shows sha256 truncated', async () => {
    mockFetch(200, { workspace_id: 'ws-1', bindings: SAMPLE_BINDINGS });
    render(<WorkspaceResourcesTab workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('deadbeef0011')).not.toBeNull();
    });
  });

  it('handles 404 gracefully', async () => {
    mockFetch(404, {});
    render(<WorkspaceResourcesTab workspaceId="missing-ws" />);
    await waitFor(() => {
      expect(screen.queryByText('No resource file bindings for this workspace.')).not.toBeNull();
    });
  });

  it('shows loading state', () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => undefined));
    render(<WorkspaceResourcesTab workspaceId="ws-1" />);
    expect(screen.queryByText('loading workspace resources…')).not.toBeNull();
  });
});
