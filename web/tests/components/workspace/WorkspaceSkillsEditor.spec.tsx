import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/http', () => ({ apiRequest: vi.fn() }));

import { apiRequest } from '@/api/http';
import WorkspaceSkillsEditor from '@/components/workspace/WorkspaceSkillsEditor';

const api = apiRequest as unknown as ReturnType<typeof vi.fn>;
const PATH = '/api/workspaces/ws1/skill-bindings';

const skill = (id: string, bound: boolean) => ({
  id,
  slug: `${id}/slug`,
  display_name: id.toUpperCase(),
  description: null,
  bound,
});

// The bound-set that the last PUT sent.
function putIds(): string[] {
  const call = api.mock.calls.find((c) => c[1]?.method === 'PUT');
  return JSON.parse(call![1].body).skill_resource_ids;
}

describe('WorkspaceSkillsEditor', () => {
  beforeEach(() => api.mockReset());

  it('GETs the skill bindings on mount and renders the rows', async () => {
    api.mockResolvedValueOnce({ items: [skill('skill-a', false), skill('skill-b', true)] });

    render(<WorkspaceSkillsEditor workspaceId="ws1" />);

    expect(await screen.findByText('SKILL-A')).toBeTruthy();
    expect(api).toHaveBeenCalledWith(PATH);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(boxes[0].checked).toBe(false); // skill-a unbound
    expect(boxes[1].checked).toBe(true); // skill-b bound
    expect(screen.getByText(/1 \/ 2 bound/)).toBeTruthy();
  });

  it('binding a skill and saving PUTs the id set including it', async () => {
    api.mockResolvedValueOnce({ items: [skill('skill-a', false), skill('skill-b', true)] });
    const user = userEvent.setup();

    render(<WorkspaceSkillsEditor workspaceId="ws1" />);
    await screen.findByText('SKILL-A');

    const save = screen.getByRole('button', { name: /Save/ }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    api.mockResolvedValueOnce(undefined); // PUT
    api.mockResolvedValueOnce({ items: [skill('skill-a', true), skill('skill-b', true)] }); // reload
    await user.click(screen.getAllByRole('checkbox')[0]); // bind skill-a
    expect(save.disabled).toBe(false);
    await user.click(save);

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(PATH, expect.objectContaining({ method: 'PUT' })),
    );
    expect(putIds()).toContain('skill-a');
    expect(putIds()).toContain('skill-b');
  });

  it('unbinding a skill and saving PUTs the set without it', async () => {
    api.mockResolvedValueOnce({ items: [skill('skill-b', true)] });
    const user = userEvent.setup();

    render(<WorkspaceSkillsEditor workspaceId="ws1" />);
    await screen.findByText('SKILL-B');

    api.mockResolvedValueOnce(undefined); // PUT
    api.mockResolvedValueOnce({ items: [skill('skill-b', false)] }); // reload
    await user.click(screen.getAllByRole('checkbox')[0]); // unbind skill-b
    await user.click(screen.getByRole('button', { name: /Save/ }));

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(PATH, expect.objectContaining({ method: 'PUT' })),
    );
    expect(putIds()).not.toContain('skill-b');
  });
});
