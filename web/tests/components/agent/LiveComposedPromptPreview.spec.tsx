import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import LiveComposedPromptPreview, {
  type PreviewResult,
} from '@/components/agent/LiveComposedPromptPreview';

const base: PreviewResult = {
  rendered_prompt: '# Hello\n\nworld',
  unresolved_markers: [],
  warnings: [],
  references: [],
  input_schema: null,
  output_schema: null,
  raw_text_output: false,
};

describe('LiveComposedPromptPreview', () => {
  it('renders the prompt as markdown', () => {
    const { container } = render(<LiveComposedPromptPreview preview={base} />);
    expect(container.querySelector('h1')?.textContent).toBe('Hello');
  });

  it('shows the total char count derived from rendered_prompt', () => {
    const { getByText } = render(<LiveComposedPromptPreview preview={base} />);
    expect(getByText(base.rendered_prompt.length.toLocaleString())).not.toBeNull();
  });

  it('shows raw-text tag when raw_text_output is true', () => {
    const { queryByText, rerender } = render(
      <LiveComposedPromptPreview preview={base} />,
    );
    expect(queryByText('raw-text output')).toBeNull();
    rerender(<LiveComposedPromptPreview preview={{ ...base, raw_text_output: true }} />);
    expect(queryByText('raw-text output')).not.toBeNull();
  });

  it('lists warnings when present', () => {
    const { getByText } = render(
      <LiveComposedPromptPreview
        preview={{ ...base, warnings: ['missing binding'] }}
      />,
    );
    expect(getByText('missing binding')).not.toBeNull();
  });

  it('renders the char breakdown bar segments', () => {
    const { container } = render(
      <LiveComposedPromptPreview
        preview={{
          ...base,
          total_chars: 100,
          char_breakdown: [
            { label: 'system', chars: 60 },
            { label: 'user', chars: 40 },
          ],
        }}
      />,
    );
    expect(container.querySelectorAll('[title^="system:"]').length).toBe(1);
    expect(container.querySelectorAll('[title^="user:"]').length).toBe(1);
  });
});
