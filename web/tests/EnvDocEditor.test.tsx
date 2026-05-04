import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import EnvDocEditor from '../src/components/EnvDocEditor';

global.fetch = vi.fn();

function mockFetch(status: number, body: object | null) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

describe('EnvDocEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders heading', async () => {
    mockFetch(200, { workspace_id: 'ws-1', content: '# ENV\nFOO=bar', path: '.env.md' });
    render(<EnvDocEditor workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('Env Doc')).not.toBeNull();
    });
  });

  it('displays env-doc content in pre block', async () => {
    mockFetch(200, { workspace_id: 'ws-1', content: 'SOME_ENV_CONTENT', path: '.env.md' });
    render(<EnvDocEditor workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('SOME_ENV_CONTENT')).not.toBeNull();
    });
  });

  it('shows path when provided', async () => {
    mockFetch(200, { workspace_id: 'ws-1', content: '# ENV', path: '.env.md' });
    render(<EnvDocEditor workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('.env.md')).not.toBeNull();
    });
  });

  it('shows empty state when content is empty', async () => {
    mockFetch(200, { workspace_id: 'ws-1', content: '', path: null });
    render(<EnvDocEditor workspaceId="ws-1" />);
    await waitFor(() => {
      expect(screen.queryByText('No env-doc found for this workspace.')).not.toBeNull();
    });
  });

  it('shows empty state on 404', async () => {
    mockFetch(404, null);
    render(<EnvDocEditor workspaceId="missing-ws" />);
    await waitFor(() => {
      expect(screen.queryByText('No env-doc found for this workspace.')).not.toBeNull();
    });
  });

  it('shows loading state initially', () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => undefined));
    render(<EnvDocEditor workspaceId="ws-1" />);
    expect(screen.queryByText('loading env-doc…')).not.toBeNull();
  });
});
