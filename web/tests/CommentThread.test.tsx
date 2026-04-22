import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CommentThread from '../src/components/CommentThread';
import * as versionsApi from '../src/api/versions';

vi.mock('../src/api/versions');

describe('CommentThread', () => {
  const mockComments = [
    {
      id: 'c1',
      version_id: 'v1',
      author: 'alice',
      body: 'Great version!',
      created_at: '2024-05-20T10:00:00Z',
      updated_at: '2024-05-20T10:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    (versionsApi.versionsApi.getComments as any).mockResolvedValue({
      version_id: 'v1',
      comments: mockComments,
    });
  });

  it('loads and displays comments', async () => {
    render(<CommentThread versionId="v1" />);

    await waitFor(() => {
      expect(screen.getByText('Great version!')).toBeInTheDocument();
      expect(screen.getByText('alice')).toBeInTheDocument();
    });
  });

  it('shows "no comments" message when empty', async () => {
    (versionsApi.versionsApi.getComments as any).mockResolvedValue({
      version_id: 'v1',
      comments: [],
    });

    render(<CommentThread versionId="v1" />);

    await waitFor(() => {
      expect(screen.getByText('No comments yet.')).toBeInTheDocument();
    });
  });

  it('posts a new comment', async () => {
    const user = userEvent.setup();
    const newComment = {
      id: 'c2',
      version_id: 'v1',
      author: 'bob',
      body: 'I agree',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    (versionsApi.versionsApi.postComment as any).mockResolvedValue(newComment);

    render(<CommentThread versionId="v1" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Add a comment...')).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText('Add a comment...');
    const submitButton = screen.getByText('Post Comment');

    await user.type(textarea, 'I agree');
    await user.click(submitButton);

    expect(versionsApi.versionsApi.postComment).toHaveBeenCalledWith('v1', 'I agree');

    await waitFor(() => {
      expect(screen.getByText('I agree')).toBeInTheDocument();
    });
  });

  it('disables submit when text is empty', async () => {
    render(<CommentThread versionId="v1" />);

    await waitFor(() => {
      const submitButton = screen.getByText('Post Comment');
      expect(submitButton).toBeDisabled();
    });
  });

  it('clears textarea after successful post', async () => {
    const user = userEvent.setup();
    (versionsApi.versionsApi.postComment as any).mockResolvedValue({
      id: 'c2',
      version_id: 'v1',
      author: 'bob',
      body: 'Test',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(<CommentThread versionId="v1" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Add a comment...')).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText('Add a comment...') as HTMLTextAreaElement;
    await user.type(textarea, 'Test comment');
    await user.click(screen.getByText('Post Comment'));

    await waitFor(() => {
      expect(textarea.value).toBe('');
    });
  });

  it('handles comment loading error', async () => {
    (versionsApi.versionsApi.getComments as any).mockRejectedValue(
      new Error('Network error')
    );

    render(<CommentThread versionId="v1" />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load comments')).toBeInTheDocument();
    });
  });
});
