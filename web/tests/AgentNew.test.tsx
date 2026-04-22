import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import AgentNew from '../src/pages/AgentNew';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

global.fetch = vi.fn();

describe('AgentNew', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders form with all fields', () => {
    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    expect(screen.getByText('Create New Agent')).toBeInTheDocument();
    expect(screen.getByLabelText('Agent ID *')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    expect(screen.getByText('Format')).toBeInTheDocument();
    expect(screen.getByLabelText('Content *')).toBeInTheDocument();
  });

  it('validates agent ID format', async () => {
    const user = userEvent.setup();

    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const idInput = screen.getByLabelText('Agent ID *');

    // Valid ID
    await user.type(idInput, 'my-agent');
    fireEvent.blur(idInput);
    expect(screen.queryByText(/must contain only/)).not.toBeInTheDocument();

    // Invalid ID with spaces
    await user.clear(idInput);
    await user.type(idInput, 'my agent');
    fireEvent.blur(idInput);
    expect(screen.getByText(/must contain only/)).toBeInTheDocument();
  });

  it('requires agent ID', async () => {
    const user = userEvent.setup();

    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const submitButton = screen.getByText('Create Agent');
    expect(submitButton).toBeDisabled();
  });

  it('shows markdown template by default', () => {
    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const textarea = screen.getByLabelText('Content *');
    expect(textarea).toHaveValue(expect.stringContaining('# Instructions'));
  });

  it('switches to TOML template', async () => {
    const user = userEvent.setup();

    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const tomlButton = screen.getAllByRole('button').find(b => b.textContent === 'TOML');
    if (tomlButton) {
      await user.click(tomlButton);

      const textarea = screen.getByLabelText('Content *');
      expect(textarea).toHaveValue(expect.stringContaining('[agent]'));
    }
  });

  it('resets template when Reset Template is clicked', async () => {
    const user = userEvent.setup();

    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const textarea = screen.getByLabelText('Content *') as HTMLTextAreaElement;
    const originalContent = textarea.value;

    // Modify content
    await user.clear(textarea);
    await user.type(textarea, 'Modified content');
    expect(textarea.value).toBe('Modified content');

    // Reset
    const resetButton = screen.getByText('Reset Template');
    await user.click(resetButton);

    expect(textarea.value).toBe(originalContent);
  });

  it('submits form with valid data', async () => {
    const user = userEvent.setup();
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as any);

    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const idInput = screen.getByLabelText('Agent ID *');
    const descInput = screen.getByLabelText('Description');
    const contentInput = screen.getByLabelText('Content *');
    const submitButton = screen.getByText('Create Agent');

    await user.type(idInput, 'test-agent');
    await user.type(descInput, 'Test agent description');
    await user.clear(contentInput);
    await user.type(contentInput, 'Test content');

    await user.click(submitButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/agents',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });
  });

  it('shows error message on submit failure', async () => {
    const user = userEvent.setup();
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Agent ID already exists' }),
    } as any);

    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const idInput = screen.getByLabelText('Agent ID *');
    const contentInput = screen.getByLabelText('Content *');
    const submitButton = screen.getByText('Create Agent');

    await user.type(idInput, 'test-agent');
    await user.clear(contentInput);
    await user.type(contentInput, 'Test content');
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText('Agent ID already exists')).toBeInTheDocument();
    });
  });

  it('disables form during submission', async () => {
    const user = userEvent.setup();
    const mockFetch = vi.mocked(global.fetch);
    mockFetch.mockImplementation(
      () =>
        new Promise(resolve =>
          setTimeout(() => resolve({ ok: true, json: async () => ({}) } as any), 100)
        )
    );

    render(
      <BrowserRouter>
        <AgentNew />
      </BrowserRouter>
    );

    const idInput = screen.getByLabelText('Agent ID *');
    const submitButton = screen.getByText('Create Agent');

    await user.type(idInput, 'test-agent');
    await user.click(submitButton);

    expect(idInput).toBeDisabled();
    expect(submitButton).toHaveTextContent('Creating...');
  });
});
