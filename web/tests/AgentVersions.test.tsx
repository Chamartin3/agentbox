import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AgentVersions from '../src/pages/AgentVersions';
import * as versionsApi from '../src/api/versions';

vi.mock('../src/api/versions');

describe('AgentVersions', () => {
  const mockVersions = [
    {
      id: 'v1',
      version: 1,
      author: 'alice',
      changelog: 'Initial version',
      is_legacy: false,
      created_at: '2024-05-20T10:00:00Z',
      has_comments: true,
      rating: 5,
    },
    {
      id: 'v2',
      version: 2,
      author: 'bob',
      changelog: 'Bug fixes',
      is_legacy: false,
      created_at: '2024-05-21T10:00:00Z',
      has_comments: false,
      rating: null,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    (versionsApi.versionsApi.listVersions as any).mockResolvedValue({
      agent_id: 'test-agent',
      latest_version: 2,
      versions: mockVersions,
    });
  });

  it('renders version list', async () => {
    render(
      <AgentVersions agentId="test-agent" />
    );

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeInTheDocument();
      expect(screen.getByText('v2')).toBeInTheDocument();
    });
  });

  it('filters versions by has-comments', async () => {
    const user = userEvent.setup();
    render(<AgentVersions agentId="test-agent" />);

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeInTheDocument();
    });

    const selects = screen.getAllByRole('combobox');
    const filterSelect = selects[0];
    await user.selectOptions(filterSelect, 'has-comments');

    // Only v1 should be visible (has comments)
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.queryByText('v2')).not.toBeInTheDocument();
  });

  it('filters versions by has-rating', async () => {
    const user = userEvent.setup();
    render(<AgentVersions agentId="test-agent" />);

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeInTheDocument();
    });

    const selects = screen.getAllByRole('combobox');
    const filterSelect = selects[0];
    await user.selectOptions(filterSelect, 'has-rating');

    // Only v1 should be visible (has rating)
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.queryByText('v2')).not.toBeInTheDocument();
  });

  it('sorts versions oldest first', async () => {
    const user = userEvent.setup();
    render(<AgentVersions agentId="test-agent" />);

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeInTheDocument();
    });

    const selects = screen.getAllByRole('combobox');
    const sortSelect = selects[1];
    await user.selectOptions(sortSelect, 'oldest');

    const rows = screen.getAllByRole('row');
    // First row is header, second should be v1 (oldest)
    expect(rows[1]).toHaveTextContent('v1');
    expect(rows[2]).toHaveTextContent('v2');
  });

  it('calls onSelectVersion when View button is clicked', async () => {
    const user = userEvent.setup();
    const onSelectVersion = vi.fn();

    render(
      <AgentVersions agentId="test-agent" onSelectVersion={onSelectVersion} />
    );

    await waitFor(() => {
      expect(screen.getAllByText('View')).toHaveLength(2);
    });

    const viewButtons = screen.getAllByText('View');
    await user.click(viewButtons[0]);

    expect(onSelectVersion).toHaveBeenCalledWith('v1', 1);
  });

  it('shows confirmation dialog on rollback', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    (versionsApi.versionsApi.rollback as any).mockResolvedValue(undefined);

    render(<AgentVersions agentId="test-agent" />);

    await waitFor(() => {
      expect(screen.getAllByText('Rollback')).toHaveLength(2);
    });

    const rollbackButtons = screen.getAllByText('Rollback');
    await user.click(rollbackButtons[0]);

    expect(confirmSpy).toHaveBeenCalledWith(
      'Are you sure you want to rollback to this version?'
    );
    expect(versionsApi.versionsApi.rollback).not.toHaveBeenCalled();

    confirmSpy.mockRestore();
  });

  it('calls rollback when confirmed', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    (versionsApi.versionsApi.rollback as any).mockResolvedValue(undefined);

    render(<AgentVersions agentId="test-agent" />);

    await waitFor(() => {
      expect(screen.getAllByText('Rollback')).toHaveLength(2);
    });

    const rollbackButtons = screen.getAllByText('Rollback');
    await user.click(rollbackButtons[0]);

    expect(versionsApi.versionsApi.rollback).toHaveBeenCalledWith('test-agent', 'v1');
  });

  it('disables rollback for legacy versions', async () => {
    const legacyVersions = [
      {
        ...mockVersions[0],
        is_legacy: true,
      },
    ];

    (versionsApi.versionsApi.listVersions as any).mockResolvedValue({
      agent_id: 'test-agent',
      latest_version: 1,
      versions: legacyVersions,
    });

    render(<AgentVersions agentId="test-agent" />);

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeInTheDocument();
    });

    const rollbackButtons = screen.queryAllByText('Rollback');
    expect(rollbackButtons).toHaveLength(0); // Should not be present for legacy
  });

  it('shows comment indicator when version has comments', async () => {
    render(<AgentVersions agentId="test-agent" />);

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeInTheDocument();
    });

    const rows = screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('💬'); // v1 has comments
  });
});
