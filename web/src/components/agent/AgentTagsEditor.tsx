import { useState, KeyboardEvent } from 'react';

interface Props {
  tags: string[];
  onChange: (tags: string[]) => void;
}

export function AgentTagsEditor({ tags, onChange }: Props) {
  const [input, setInput] = useState('');

  const addTag = (raw: string) => {
    const trimmed = raw.trim().replace(/,$/, '').trim();
    if (!trimmed || tags.includes(trimmed)) { setInput(''); return; }
    onChange([...tags, trimmed]);
    setInput('');
  };

  const removeTag = (t: string) => onChange(tags.filter((x) => x !== t));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',' || e.key === 'Tab') {
      if (input.trim()) { e.preventDefault(); addTag(input); }
    } else if (e.key === 'Backspace' && !input && tags.length > 0) {
      removeTag(tags[tags.length - 1]);
    }
  };

  return (
    <div
      className="tag-chip-input"
      onClick={(e) => {
        if ((e.target as HTMLElement).tagName !== 'INPUT') {
          (e.currentTarget as HTMLElement).querySelector('input')?.focus();
        }
      }}
    >
      {tags.map((t) => (
        <span
          key={t}
          className="tag"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 6px', fontSize: 12 }}
        >
          {t}
          <button
            type="button"
            aria-label={`remove ${t}`}
            onClick={(e) => { e.stopPropagation(); removeTag(t); }}
            style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer', fontSize: 12, lineHeight: 1, color: 'inherit' }}
          >×</button>
        </span>
      ))}
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => { if (input.trim()) addTag(input); }}
        placeholder={tags.length === 0 ? 'add tags…' : ''}
        style={{ flex: 1, minWidth: 80, border: 'none', outline: 'none', background: 'transparent', padding: '2px 4px' }}
      />
    </div>
  );
}
