import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/http', () => ({ apiRequest: vi.fn() }));
// The component imports MarkdownEditor which itself uses an editor lib; stub it.
vi.mock('@/components/common/MarkdownEditor', () => ({
  default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea
      data-testid="md"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

import { apiRequest } from '@/api/http';
import EnvDocEditor from '@/components/workspace/EnvDocEditor';

const req = apiRequest as unknown as ReturnType<typeof vi.fn>;

describe('EnvDocEditor', () => {
  beforeEach(() => req.mockReset());

  it('loads the active env-doc and renders the overview', async () => {
    req.mockResolvedValueOnce({
      active: { content_json: { overview: 'hello world' } },
    });
    render(<EnvDocEditor workspaceId="ws1" />);
    await waitFor(() => {
      expect((screen.getByTestId('md') as HTMLTextAreaElement).value).toBe('hello world');
    });
    expect(req).toHaveBeenCalledWith('/api/workspaces/ws1/env-doc');
  });

  it('Save is disabled until the overview changes, then PUTs the content', async () => {
    req.mockResolvedValueOnce({ active: { content_json: { overview: 'a' } } });
    const user = userEvent.setup();
    render(<EnvDocEditor workspaceId="ws1" />);

    await waitFor(() => screen.getByTestId('md'));
    const save = screen.getByRole('button', { name: /Save/ }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    req.mockResolvedValueOnce(undefined); // PUT
    req.mockResolvedValueOnce({ active: { content_json: { overview: 'ab' } } }); // reload
    await user.type(screen.getByTestId('md'), 'b');
    expect(save.disabled).toBe(false);

    await user.click(save);
    await waitFor(() =>
      expect(req).toHaveBeenCalledWith(
        '/api/workspaces/ws1/env-doc',
        expect.objectContaining({ method: 'PUT' }),
      ),
    );
  });

  it('falls back to an empty doc when none is active', async () => {
    req.mockResolvedValueOnce({ active: null });
    render(<EnvDocEditor workspaceId="ws1" />);
    await waitFor(() => {
      expect((screen.getByTestId('md') as HTMLTextAreaElement).value).toBe('');
    });
  });
});
