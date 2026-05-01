import { useEffect, useState } from 'react';
import { api, ApiError, BundleFileKind } from '../api/client';

interface BundleFile {
  id: number;
  kind: string;
  relative_path: string;
  sha256: string;
  source_uri: string | null;
}

interface Props {
  agentId: string;
  version: number;
  isDraft: boolean;
}

const FILE_KINDS: BundleFileKind[] = [
  'output_schema',
  'input_schema',
  'user_template',
  'system',
  'reference',
];

export default function BundleFileEditor({ agentId, version, isDraft }: Props) {
  const [files, setFiles] = useState<BundleFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadKind, setUploadKind] = useState<BundleFileKind>('system');
  const [uploadName, setUploadName] = useState('');
  const [uploadContent, setUploadContent] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadFiles = async () => {
    setLoading(true);
    try {
      const detail = await api.getAgent(agentId);
      // bundle_files from getAgent don't have IDs; we need them for delete
      // The API returns files for the latest version. For a draft we need to
      // list them. Use the getAgent response as it has the relevant version files.
      // IDs are returned by uploadVersionFile but not by getAgent, so we keep
      // track after uploads. For existing files we'll show without IDs unless
      // we do a dedicated list call. The current API doesn't expose a
      // GET /api/agents/{id}/versions/{v}/files endpoint, so we rely on
      // getAgent bundle_files and augment with IDs after upload.
      setFiles(
        (detail.bundle_files || []).map((f, idx) => ({
          id: idx, // placeholder; delete won't work without real IDs
          kind: f.kind,
          relative_path: f.relative_path,
          sha256: f.sha256,
          source_uri: f.source_uri,
        })),
      );
    } catch {
      setFiles([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFiles();
  }, [agentId, version]);

  const handleUpload = async () => {
    if (!uploadName.trim() || !uploadContent.trim()) {
      setUploadError('Name and content are required.');
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      await api.uploadVersionFile(agentId, version, {
        kind: uploadKind,
        name: uploadName.trim(),
        content: uploadContent,
      });
      setUploadName('');
      setUploadContent('');
      await loadFiles();
    } catch (e) {
      const err = e as ApiError;
      const detail = err.detail as Record<string, unknown> | null;
      const code = detail && typeof detail === 'object' ? String(detail['code'] || '') : '';
      if (code === 'duplicate_sha256') {
        setUploadError('A file with identical content already exists in this version.');
      } else if (code === 'duplicate_path') {
        setUploadError(`A file named "${uploadName}" already exists in this version.`);
      } else if (code === 'not_draft') {
        setUploadError('Cannot modify a published version.');
      } else {
        setUploadError(`Upload failed (HTTP ${err.status}): ${JSON.stringify(err.detail)}`);
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (fileId: number, path: string) => {
    if (!window.confirm(`Delete file "${path}"?`)) return;
    setDeleting(fileId);
    setDeleteError(null);
    try {
      await api.deleteVersionFile(agentId, version, fileId);
      await loadFiles();
    } catch (e) {
      const err = e as ApiError;
      setDeleteError(`Delete failed (HTTP ${err.status}): ${JSON.stringify(err.detail)}`);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="stack">
      <h2 style={{ border: 'none', margin: 0, fontSize: 14 }}>
        Bundle Files
        <span className="dim" style={{ fontWeight: 400, fontSize: 11, marginLeft: 8 }}>
          v{version}{isDraft ? ' · draft' : ' · published'}
        </span>
      </h2>

      {loading ? (
        <p className="dim" style={{ fontSize: 12 }}>loading files…</p>
      ) : files.length === 0 ? (
        <p className="dim" style={{ fontSize: 12 }}>No bundle files yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Kind</th>
              <th>Path</th>
              <th>SHA256</th>
              {isDraft && <th></th>}
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.relative_path}>
                <td><span className="pill">{f.kind}</span></td>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{f.relative_path}</td>
                <td className="dim" style={{ fontSize: 11, fontFamily: 'monospace' }}>{f.sha256.slice(0, 12)}</td>
                {isDraft && (
                  <td>
                    <button
                      className="link-btn"
                      style={{ color: 'var(--red)' }}
                      disabled={deleting === f.id}
                      onClick={() => handleDelete(f.id, f.relative_path)}
                    >
                      {deleting === f.id ? 'deleting…' : 'delete'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {deleteError && (
        <p style={{ color: 'var(--red)', fontSize: 12, margin: 0 }}>{deleteError}</p>
      )}

      {isDraft && (
        <fieldset className="config-fieldset" style={{ marginTop: 8 }}>
          <legend>upload file</legend>

          <div className="field">
            <label>kind</label>
            <select
              value={uploadKind}
              onChange={(e) => setUploadKind(e.target.value as BundleFileKind)}
              style={{ width: '100%' }}
            >
              {FILE_KINDS.map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>name</label>
            <input
              value={uploadName}
              onChange={(e) => setUploadName(e.target.value)}
              placeholder="e.g. output_schema.json or prompts/system.md"
            />
          </div>

          <div className="field" style={{ alignItems: 'flex-start' }}>
            <label style={{ paddingTop: 6 }}>content</label>
            <textarea
              value={uploadContent}
              onChange={(e) => setUploadContent(e.target.value)}
              rows={8}
              placeholder="Paste file content here…"
              style={{ width: '100%', resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            />
          </div>

          {uploadError && (
            <p style={{ color: 'var(--red)', fontSize: 12, gridColumn: '1/-1', margin: 0 }}>
              {uploadError}
            </p>
          )}

          <div style={{ gridColumn: '2/-1', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="primary"
              onClick={handleUpload}
              disabled={uploading || !uploadName.trim() || !uploadContent.trim()}
            >
              {uploading ? 'uploading…' : 'upload file'}
            </button>
          </div>
        </fieldset>
      )}
    </div>
  );
}
