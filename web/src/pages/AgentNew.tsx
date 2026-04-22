import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './AgentNew.css';

type Format = 'markdown' | 'standalone_toml';

export default function AgentNew() {
  const navigate = useNavigate();
  const [format, setFormat] = useState<Format>('markdown');
  const [agentId, setAgentId] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idError, setIdError] = useState<string | null>(null);

  const validateAgentId = (id: string) => {
    if (!id) {
      setIdError('Agent ID is required');
      return false;
    }
    if (!/^[a-z0-9_-]+$/.test(id)) {
      setIdError('Agent ID must contain only lowercase letters, numbers, underscores, and hyphens');
      return false;
    }
    setIdError(null);
    return true;
  };

  const handleIdBlur = () => {
    validateAgentId(agentId);
  };

  const getTemplate = () => {
    if (format === 'markdown') {
      return `# ${agentId || 'Agent Name'}

${description || 'Brief description of what this agent does.'}

## Instructions

Add detailed instructions for the agent here.
- What is the agent's purpose?
- What tools does it use?
- Any important constraints?

## Examples

Provide examples of how the agent should behave.
`;
    } else {
      return `# TOML format agent

[agent]
id = "${agentId || 'agent-id'}"
description = "${description || 'Agent description'}"
runner.kind = "pydantic_ai"

[[agent.tools]]
name = "Read"
`;
    }
  };

  const handleFormatChange = (newFormat: Format) => {
    setFormat(newFormat);
    setContent(getTemplate());
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateAgentId(agentId)) return;
    if (!content.trim()) {
      setError('Content cannot be empty');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const resp = await fetch('/api/agents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: agentId,
          description,
          format,
          content,
        }),
      });

      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.detail || 'Failed to create agent');
      }

      // Navigate to the new agent detail page
      navigate(`/agents/${agentId}`);
    } catch (err) {
      console.error('Failed to create agent:', err);
      setError(err instanceof Error ? err.message : 'Failed to create agent');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="agent-new">
      <h1>Create New Agent</h1>

      <form onSubmit={handleSave} className="new-agent-form">
        {error && <div className="error-message">{error}</div>}

        <div className="form-group">
          <label htmlFor="agentId">Agent ID *</label>
          <input
            id="agentId"
            type="text"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            onBlur={handleIdBlur}
            placeholder="my-agent (lowercase, hyphens, underscores only)"
            disabled={isLoading}
          />
          {idError && <span className="field-error">{idError}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="description">Description</label>
          <input
            id="description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief description of the agent"
            disabled={isLoading}
          />
        </div>

        <div className="form-group">
          <label>Format</label>
          <div className="format-toggle">
            <button
              type="button"
              className={`format-btn ${format === 'markdown' ? 'active' : ''}`}
              onClick={() => handleFormatChange('markdown')}
              disabled={isLoading}
            >
              Markdown
            </button>
            <button
              type="button"
              className={`format-btn ${format === 'standalone_toml' ? 'active' : ''}`}
              onClick={() => handleFormatChange('standalone_toml')}
              disabled={isLoading}
            >
              TOML
            </button>
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="content">Content *</label>
          <textarea
            id="content"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={15}
            disabled={isLoading}
            required
          />
        </div>

        <div className="form-actions">
          <button
            type="submit"
            className="btn-primary"
            disabled={isLoading || !agentId || !content.trim()}
          >
            {isLoading ? 'Creating...' : 'Create Agent'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => navigate('/agents')}
            disabled={isLoading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setContent(getTemplate())}
            disabled={isLoading}
          >
            Reset Template
          </button>
        </div>
      </form>
    </div>
  );
}
