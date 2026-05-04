import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import PromptBindingsEditor from '../src/components/PromptBindingsEditor';

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
    marker: '{{SKILL_REF}}',
    resource_id: 'my-skill',
    resource_version: 3,
    kind: 'skill',
    name: 'My Skill',
  },
  {
    marker: '{{SCHEMA}}',
    resource_id: 'output-schema',
    resource_version: null,
    kind: 'output_schema',
    name: 'Output Schema',
  },
];

describe('PromptBindingsEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders section heading', async () => {
    mockFetch(200, { agent_id: 'agent-1', bindings: SAMPLE_BINDINGS });
    render(<PromptBindingsEditor agentId="agent-1" />);
    await waitFor(() => {
      expect(screen.queryByText('Prompt Bindings')).not.toBeNull();
    });
  });

  it('shows empty state when no bindings', async () => {
    mockFetch(200, { agent_id: 'agent-1', bindings: [] });
    render(<PromptBindingsEditor agentId="agent-1" />);
    await waitFor(() => {
      expect(screen.queryByText('No prompt bindings configured for this agent.')).not.toBeNull();
    });
  });

  it('renders binding rows', async () => {
    mockFetch(200, { agent_id: 'agent-1', bindings: SAMPLE_BINDINGS });
    render(<PromptBindingsEditor agentId="agent-1" />);
    await waitFor(() => {
      expect(screen.queryByText('{{SKILL_REF}}')).not.toBeNull();
      expect(screen.queryByText('my-skill')).not.toBeNull();
      expect(screen.queryByText('{{SCHEMA}}')).not.toBeNull();
      expect(screen.queryByText('output-schema')).not.toBeNull();
    });
  });

  it('shows pinned version badge', async () => {
    mockFetch(200, { agent_id: 'agent-1', bindings: SAMPLE_BINDINGS });
    render(<PromptBindingsEditor agentId="agent-1" />);
    await waitFor(() => {
      expect(screen.queryByText('v3')).not.toBeNull();
      expect(screen.queryByText('latest')).not.toBeNull();
    });
  });

  it('handles 404 gracefully', async () => {
    mockFetch(404, {});
    render(<PromptBindingsEditor agentId="missing-agent" />);
    await waitFor(() => {
      expect(screen.queryByText('No prompt bindings configured for this agent.')).not.toBeNull();
    });
  });

  it('shows loading state initially', () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => undefined));
    render(<PromptBindingsEditor agentId="agent-1" />);
    expect(screen.queryByText('loading prompt bindings…')).not.toBeNull();
  });

  it('shows table column headers', async () => {
    mockFetch(200, { agent_id: 'agent-1', bindings: SAMPLE_BINDINGS });
    render(<PromptBindingsEditor agentId="agent-1" />);
    await waitFor(() => {
      expect(screen.queryByText('Marker')).not.toBeNull();
      expect(screen.queryByText('Resource ID')).not.toBeNull();
      expect(screen.queryByText('Version')).not.toBeNull();
    });
  });
});
