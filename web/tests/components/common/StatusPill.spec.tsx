import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { StatusPill } from '@/components/common/StatusPill';

describe('StatusPill', () => {
  it.each([
    ['ok', 'ok'],
    ['running', 'running'],
    ['error', 'error'],
    ['failed', 'failed'],
    ['timeout', 'timeout'],
  ])('renders %s with class %s', (status, cls) => {
    const { container } = render(<StatusPill status={status} />);
    const el = container.querySelector('.pill');
    expect(el).not.toBeNull();
    expect(el?.className).toContain(cls);
    expect(el?.textContent).toBe(status);
  });

  it('canonicalizes alias to ok class but keeps label', () => {
    const { container } = render(<StatusPill status="succeeded" />);
    const el = container.querySelector('.pill');
    expect(el?.className).toContain('ok');
    expect(el?.textContent).toBe('ok');
  });
});
