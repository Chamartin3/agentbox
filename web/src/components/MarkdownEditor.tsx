import CodeMirror from '@uiw/react-codemirror';
import { markdown } from '@codemirror/lang-markdown';
import { githubDark } from '@uiw/codemirror-theme-github';
import { EditorView } from '@codemirror/view';

interface Props {
  value: string;
  onChange: (v: string) => void;
  height?: string;
}

export default function MarkdownEditor({ value, onChange, height = '60vh' }: Props) {
  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      height={height}
      theme={githubDark}
      extensions={[markdown(), EditorView.lineWrapping]}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLine: true,
        foldGutter: false,
      }}
    />
  );
}
