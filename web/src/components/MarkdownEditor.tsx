import CodeMirror from '@uiw/react-codemirror';
import { markdown } from '@codemirror/lang-markdown';
import { githubDark } from '@uiw/codemirror-theme-github';
import { EditorView } from '@codemirror/view';

interface Props {
  value: string;
  onChange: (v: string) => void;
  /** Default initial height. User can drag-resize vertically from there. */
  height?: string;
}

export default function MarkdownEditor({ value, onChange, height = '18em' }: Props) {
  return (
    <div
      style={{
        resize: 'vertical',
        overflow: 'hidden',
        minHeight: 80,
        height,
        border: '1px solid var(--border, #333)',
        borderRadius: 4,
      }}
    >
      <CodeMirror
        value={value}
        onChange={onChange}
        height="100%"
        style={{ height: '100%' }}
        theme={githubDark}
        extensions={[markdown(), EditorView.lineWrapping]}
        basicSetup={{
          lineNumbers: true,
          highlightActiveLine: true,
          foldGutter: false,
        }}
      />
    </div>
  );
}
