import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import ResourcesPage from '../src/pages/ResourcesPage';

global.fetch = vi.fn();

function mockListResources(items: object[], total?: number) {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ items, total: total ?? items.length }),
  });
}

const SAMPLE_RESOURCE = {
  id: 'my-schema',
  version: 2,
  kind: 'output_schema',
  name: 'My Schema',
  description: 'a test schema',
  sha256: 'abc123def456789012345678',
  is_active: true,
  tags: ['prod'],
  created_at: '2024-01-01T00:00:00Z',
};

describe('ResourcesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders heading', async () => {
    mockListResources([]);
    render(
      <BrowserRouter>
        <ResourcesPage />
      </BrowserRouter>
    );
    await waitFor(() => {
      expect(screen.queryByText('Shared Resources')).not.toBeNull();
    });
  });

  it('shows empty state when no resources', async () => {
    mockListResources([]);
    render(
      <BrowserRouter>
        <ResourcesPage />
      </BrowserRouter>
    );
    await waitFor(() => {
      expect(screen.queryByText('No resources found.')).not.toBeNull();
    });
  });

  it('renders resource rows', async () => {
    mockListResources([SAMPLE_RESOURCE]);
    render(
      <BrowserRouter>
        <ResourcesPage />
      </BrowserRouter>
    );
    await waitFor(() => {
      // queryAllByText because 'output_schema' also appears as a select option
      expect(screen.queryAllByText('output_schema').length).toBeGreaterThan(0);
      expect(screen.queryByText('My Schema')).not.toBeNull();
      expect(screen.queryAllByText('my-schema').length).toBeGreaterThan(0);
    });
  });

  it('shows active version badge', async () => {
    mockListResources([SAMPLE_RESOURCE]);
    render(
      <BrowserRouter>
        <ResourcesPage />
      </BrowserRouter>
    );
    await waitFor(() => {
      expect(screen.queryByText('v2')).not.toBeNull();
    });
  });

  it('shows total count', async () => {
    mockListResources([SAMPLE_RESOURCE], 42);
    render(
      <BrowserRouter>
        <ResourcesPage />
      </BrowserRouter>
    );
    await waitFor(() => {
      expect(screen.queryByText('42 total')).not.toBeNull();
    });
  });

  it('shows loading state initially', () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => undefined));
    render(
      <BrowserRouter>
        <ResourcesPage />
      </BrowserRouter>
    );
    expect(screen.queryByText('loading…')).not.toBeNull();
  });

  it('renders table headers', async () => {
    mockListResources([SAMPLE_RESOURCE]);
    render(
      <BrowserRouter>
        <ResourcesPage />
      </BrowserRouter>
    );
    await waitFor(() => {
      expect(screen.queryByText('ID / Slug')).not.toBeNull();
      expect(screen.queryByText('Kind')).not.toBeNull();
      expect(screen.queryByText('Name')).not.toBeNull();
      expect(screen.queryByText('Active Version')).not.toBeNull();
    });
  });
});
