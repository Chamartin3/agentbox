interface FileEntry {
  path: string;
  size: number;
  resource?: string | null;
}

interface Node {
  name: string;
  path: string;
  size?: number;
  resource?: string | null;
  children: Map<string, Node>;
}

function buildTree(files: FileEntry[]): Node {
  const root: Node = { name: '', path: '', children: new Map() };
  for (const f of files) {
    const parts = f.path.split('/');
    let node = root;
    parts.forEach((part, i) => {
      let child = node.children.get(part);
      if (!child) {
        child = { name: part, path: parts.slice(0, i + 1).join('/'), children: new Map() };
        node.children.set(part, child);
      }
      if (i === parts.length - 1) {
        child.size = f.size;
        child.resource = f.resource ?? null;
      }
      node = child;
    });
  }
  return root;
}

// Folders first, then alphabetical.
function sortedChildren(node: Node): Node[] {
  return [...node.children.values()].sort((a, b) => {
    const aDir = a.children.size > 0;
    const bDir = b.children.size > 0;
    if (aDir !== bDir) return aDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

function TreeNode({ node, depth, onOpen }: { node: Node; depth: number; onOpen: (p: string) => void }) {
  const isDir = node.children.size > 0;
  const pad = { paddingLeft: depth * 14 };
  if (isDir) {
    return (
      <details open={depth === 0} style={{ fontSize: 12 }}>
        <summary style={{ ...pad, cursor: 'pointer', padding: '2px 0' }}>📁 {node.name}</summary>
        {sortedChildren(node).map((c) => (
          <TreeNode key={c.path} node={c} depth={depth + 1} onOpen={onOpen} />
        ))}
      </details>
    );
  }
  return (
    <div className="row between" style={{ ...pad, padding: '2px 0' }}>
      <button className="link-btn" style={{ fontSize: 12 }} onClick={() => onOpen(node.path)}>
        📄 {node.name}
      </button>
      <span className="row" style={{ gap: 6, alignItems: 'center' }}>
        {node.resource && (
          <span className="pill" style={{ fontSize: 9 }} title={`from resource ${node.resource}`}>
            resource
          </span>
        )}
        <span className="dim" style={{ fontSize: 10 }}>{node.size}b</span>
      </span>
    </div>
  );
}

export default function FileTree({ files, onOpen }: { files: FileEntry[]; onOpen: (p: string) => void }) {
  const root = buildTree(files);
  return (
    <div className="stack" style={{ gap: 0 }}>
      {sortedChildren(root).map((c) => (
        <TreeNode key={c.path} node={c} depth={0} onOpen={onOpen} />
      ))}
    </div>
  );
}
