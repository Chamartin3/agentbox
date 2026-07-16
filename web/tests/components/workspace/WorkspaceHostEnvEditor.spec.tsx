import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/repo', () => ({
  hostEnvApi: {
    capabilities: vi.fn(),
    getWorkspace: vi.fn(),
    setWorkspace: vi.fn(),
  },
}));

import { hostEnvApi } from '@/api/repo';
import WorkspaceHostEnvEditor from '@/components/workspace/WorkspaceHostEnvEditor';

const capabilities = hostEnvApi.capabilities as unknown as ReturnType<typeof vi.fn>;
const getWorkspace = hostEnvApi.getWorkspace as unknown as ReturnType<typeof vi.fn>;
const setWorkspace = hostEnvApi.setWorkspace as unknown as ReturnType<typeof vi.fn>;

const cap = (name: string, default_granted = false) => ({
  name,
  description: `${name} description`,
  grant_schema: {},
  default_granted,
});

describe('WorkspaceHostEnvEditor', () => {
  beforeEach(() => {
    capabilities.mockReset();
    getWorkspace.mockReset();
    setWorkspace.mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  it('lists capabilities with the current grant state', async () => {
    capabilities.mockResolvedValueOnce({
      capabilities: [cap('fs.read'), cap('net.egress', true)],
    });
    getWorkspace.mockResolvedValueOnce({
      grants: { 'fs.read': { roots: ['/x'] } },
      profile_id: null,
    });

    render(<WorkspaceHostEnvEditor workspaceId="ws1" />);

    expect(await screen.findByText('fs.read')).toBeTruthy();
    expect(getWorkspace).toHaveBeenCalledWith('ws1');

    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    // fs.read is granted via the workspace overrides → checked & editable.
    expect(boxes[0].checked).toBe(true);
    expect(boxes[0].disabled).toBe(false);
    // net.egress is default_granted → checked & forced (disabled).
    expect(boxes[1].checked).toBe(true);
    expect(boxes[1].disabled).toBe(true);
  });

  it('toggling a grant and saving PUTs the merged grants via setWorkspace', async () => {
    capabilities.mockResolvedValue({ capabilities: [cap('fs.read')] });
    getWorkspace.mockResolvedValue({ grants: {}, profile_id: 'prof-1' });
    setWorkspace.mockResolvedValueOnce({ grants: {}, profile_id: 'prof-1' });
    vi.spyOn(window, 'prompt').mockReturnValue('granting fs.read');
    const user = userEvent.setup();

    render(<WorkspaceHostEnvEditor workspaceId="ws1" />);
    const box = (await screen.findAllByRole('checkbox'))[0] as HTMLInputElement;
    expect(box.checked).toBe(false);

    await user.click(box);
    await user.click(screen.getByRole('button', { name: /save capabilities/i }));

    await waitFor(() =>
      expect(setWorkspace).toHaveBeenCalledWith(
        'ws1',
        { 'fs.read': {} },
        'granting fs.read',
        'prof-1',
      ),
    );
  });

  it('shows the error state when the load fails', async () => {
    capabilities.mockRejectedValueOnce(new Error('boom'));
    getWorkspace.mockResolvedValueOnce({ grants: {}, profile_id: null });

    render(<WorkspaceHostEnvEditor workspaceId="ws1" />);

    expect(await screen.findByText('Error: boom')).toBeTruthy();
  });
});
