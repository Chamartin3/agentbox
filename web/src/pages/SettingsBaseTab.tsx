import { useEffect, useState } from 'react';
import { apiRequest } from '../api/http';

// Runtime defaults (harness per-backend default model + timeout). Rendered
// inside the Settings → Runner Profiles tab. The dead webhook/telemetry/
// workspace_defaults sections were removed — nothing read them at runtime.

interface SectionPayload {
  section: string;
  values: Record<string, unknown>;
  defaults?: Record<string, unknown>;
  overrides?: Record<string, unknown>;
}

export type ToastState = { kind: 'ok' | 'error'; msg: string } | null;

async function fetchSection(section: string): Promise<SectionPayload> {
  return apiRequest<SectionPayload>(`/api/settings/${section}`);
}

async function patchSection(section: string, values: Record<string, unknown>): Promise<void> {
  await apiRequest(`/api/settings/${section}`, {
    method: 'PATCH',
    body: JSON.stringify({ values }),
  });
}

function inputRow(label: string, child: React.ReactNode) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 8, alignItems: 'center' }}>
      <label style={{ fontSize: 13 }}>{label}</label>
      {child}
    </div>
  );
}

export function RuntimeDefaultsForm({ onToast }: { onToast: (t: ToastState) => void }) {
  const section = 'runtime_defaults';
  const [timeout, setTimeoutS] = useState<number | ''>('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchSection(section)
      .then((d) => {
        const v = d.values || {};
        setTimeoutS(typeof v.timeout_seconds === 'number' ? v.timeout_seconds : '');
        setLoaded(true);
      })
      .catch((e) => onToast({ kind: 'error', msg: `load failed: ${e.message}` }));
  }, [onToast]);

  async function save() {
    try {
      // Merge-patch: only the timeout. Per-harness default models are edited
      // in the Harnesses table below (same runtime_defaults section).
      await patchSection(section, {
        timeout_seconds: timeout === '' ? null : Number(timeout),
      });
      onToast({ kind: 'ok', msg: 'runtime defaults saved' });
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  if (!loaded) return <p className="dim">loading…</p>;

  return (
    <div className="stack" style={{ gap: 8 }}>
      {inputRow(
        'timeout_seconds',
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeoutS(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          placeholder="1200"
        />,
      )}
      <div>
        <button onClick={save}>save timeout</button>
      </div>
    </div>
  );
}
