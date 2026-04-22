import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AgentVersionDiff from '../src/pages/AgentVersionDiff';
import * as versionsApi from '../src/api/versions';

vi.mock('../src/api/versions');

describe('AgentVersionDiff', () => {
  const mockVersions = [
    {
      id: 'v1',
      version: 1,
      author: 'alice',
      changelog: 'Initial',
      is_legacy: false,
      created_at: '2024-05-20T10:00:00Z',
      has_comments: false,
      rating: null,
    },
    {
      id: 'v2',
      version: 2,
      author: 'bob',
      changelog: 'Updated',
      is_legacy: false,
      created_at: '2024-05-21T10:00:00Z',
      has_comments: false,
      rating: null,
    },
  ];

  const mockDiff = {
    from_version: 1,
    to_version: 2,
    agent_id: 'test',
    prompt_diff: [
      {
        type: 'removed' as const,
        lines: ['Old line 1', 'Old line 2'],
      },
      {
        type: 'added' as const,
        lines: ['New line 1'],
      },
    ],
    metadata_diff: [
      {
        key: 'timeout_seconds',
        from: 120,
        to: 180,
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (versionsApi.versionsApi.diffVersions as any).mockResolvedValue(mockDiff);
  });

  it('renders version selectors', async () => {
    render(
      <AgentVersionDiff
        agentId="test"
        latestVersion={2}
        versions={mockVersions}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('From:')).toBeInTheDocument();
      expect(screen.getByText('To:')).toBeInTheDocument();
    });
  });

  it('loads diff on version change', async () => {
    const user = userEvent.setup();

    render(
      <AgentVersionDiff
        agentId="test"
        latestVersion={2}
        versions={mockVersions}
      />
    );

    await waitFor(() => {
      expect(versionsApi.versionsApi.diffVersions).toHaveBeenCalled();
    });

    const selects = screen.getAllByRole('combobox');
    const fromSelect = selects[0];
    await user.selectOptions(fromSelect, 'v2');

    await waitFor(() => {
      expect(versionsApi.versionsApi.diffVersions).toHaveBeenCalledWith(
        'test',
        2,
        2
      );
    });
  });

  it('displays prompt diff with syntax highlighting', async () => {
    render(
      <AgentVersionDiff
        agentId="test"
        latestVersion={2}
        versions={mockVersions}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Prompt Changes')).toBeInTheDocument();
    });

    // Check for diff markers
    const diffLines = screen.getAllByText(/Old line|New line/);
    expect(diffLines.length).toBeGreaterThan(0);
  });

  it('displays metadata diff', async () => {
    render(
      <AgentVersionDiff
        agentId="test"
        latestVersion={2}
        versions={mockVersions}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Metadata Changes')).toBeInTheDocument();
      expect(screen.getByText('timeout_seconds')).toBeInTheDocument();
    });
  });

  it('shows "no changes" message when diff is empty', async () => {
    (versionsApi.versionsApi.diffVersions as any).mockResolvedValue({
      from_version: 1,
      to_version: 2,
      agent_id: 'test',
      prompt_diff: [],
      metadata_diff: [],
    });

    render(
      <AgentVersionDiff
        agentId="test"
        latestVersion={2}
        versions={mockVersions}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('No differences between these versions.')).toBeInTheDocument();
    });
  });

  it('handles diff loading error', async () => {
    (versionsApi.versionsApi.diffVersions as any).mockRejectedValue(
      new Error('Network error')
    );

    render(
      <AgentVersionDiff
        agentId="test"
        latestVersion={2}
        versions={mockVersions}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Failed to load diff')).toBeInTheDocument();
    });
  });

  it('highlights changed metadata rows', async () => {
    render(
      <AgentVersionDiff
        agentId="test"
        latestVersion={2}
        versions={mockVersions}
      />
    );

    await waitFor(() => {
      const metadataRows = screen.getAllByRole('row');
      const changedRow = metadataRows.find(row => row.textContent.includes('timeout_seconds'));
      expect(changedRow).toHaveClass('metadata-changed');
    });
  });
});
