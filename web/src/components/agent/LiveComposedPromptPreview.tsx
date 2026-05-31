import { Marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import hljs from 'highlight.js/lib/core';
import json from 'highlight.js/lib/languages/json';
import 'highlight.js/styles/github-dark.css';

hljs.registerLanguage('json', json);

const marked = new Marked(
  markedHighlight({
    emptyLangClass: 'hljs',
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(code, { language: lang }).value;
        } catch {
          /* fall through */
        }
      }
      return code;
    },
  }),
);

export interface CharPart {
  label: string;
  chars: number;
}

export interface PreviewResult {
  rendered_prompt: string;
  unresolved_markers: string[];
  warnings: string[];
  references: Array<{ binding_id: string; resource_id: string; display_name?: string | null }>;
  input_schema: { binding_id: string; resource_id: string; text: string } | null;
  output_schema: { binding_id: string; resource_id: string; text: string } | null;
  raw_text_output: boolean;
  char_breakdown?: CharPart[];
  total_chars?: number;
}

export default function LiveComposedPromptPreview({ preview }: { preview: PreviewResult }) {
  const total = preview.total_chars ?? preview.rendered_prompt.length;
  const n = preview.char_breakdown?.length ?? 0;
  const colors =
    preview.char_breakdown?.map((_, i) => `hsl(${Math.round((i * 360) / Math.max(n, 1))}, 65%, 55%)`) ?? [];

  return (
    <section className="composition-section">
      <div className="composition-section-header">
        <h3>
          Live composed prompt
          {preview.raw_text_output && (
            <span className="tag" style={{ marginLeft: 8 }}>raw-text output</span>
          )}
        </h3>
        <div className="composition-section-meta" style={{ alignItems: 'baseline' }}>
          <span style={{ fontVariantNumeric: 'tabular-nums' }}>
            <strong style={{ fontSize: 14, color: 'var(--fg)' }}>{total.toLocaleString()}</strong>
            <span style={{ marginLeft: 4 }}>chars</span>
            <span style={{ marginLeft: 8, opacity: 0.7 }}>≈ {Math.round(total / 4).toLocaleString()} tokens</span>
          </span>
        </div>
      </div>
      {preview.char_breakdown && preview.char_breakdown.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div
            style={{
              display: 'flex',
              height: 18,
              borderRadius: 4,
              overflow: 'hidden',
              border: '1px solid var(--border, #333)',
              marginBottom: 6,
            }}
          >
            {preview.char_breakdown.map((p, i) => {
              const pct = total > 0 ? (p.chars / total) * 100 : 0;
              return (
                <div
                  key={p.label}
                  title={`${p.label}: ${p.chars.toLocaleString()} chars (${pct.toFixed(1)}%)`}
                  style={{
                    background: colors[i % colors.length],
                    width: `${pct}%`,
                    minWidth: pct > 0 ? 2 : 0,
                  }}
                />
              );
            })}
          </div>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap', fontSize: 12 }}>
            {preview.char_breakdown.map((p, i) => {
              const pct = total > 0 ? (p.chars / total) * 100 : 0;
              return (
                <div key={p.label} className="row" style={{ gap: 5, alignItems: 'center' }}>
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: 2,
                      background: colors[i % colors.length],
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ fontWeight: 500 }}>{p.label}</span>
                  <span style={{ opacity: 0.8 }}>
                    {p.chars.toLocaleString()}
                    <span style={{ opacity: 0.5 }}> ({pct.toFixed(0)}%)</span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {preview.warnings.length > 0 && (
        <ul className="dim" style={{ fontSize: 11, marginTop: 4 }}>
          {preview.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      <div
        className="md-preview"
        style={{
          background: 'var(--bg-soft, #111)',
          padding: 14,
          borderRadius: 4,
          fontSize: 13,
          height: '30em',
          minHeight: 120,
          resize: 'vertical',
          overflow: 'auto',
          lineHeight: 1.5,
        }}
        dangerouslySetInnerHTML={{
          __html: marked.parse(preview.rendered_prompt || '', { async: false }) as string,
        }}
      />
    </section>
  );
}
