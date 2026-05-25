// Single source of truth for HTTP I/O against the agentbox API.
// All `fetch(...)` calls in the app should go through `apiRequest`
// (or `apiRequestOrNull` for "ok to be missing" reads).
//
// Previously every api/* module and a handful of components rolled
// their own `req<T>()` helper with subtly different error semantics —
// this module replaces all of them.

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    const tail =
      detail === undefined || detail === null || detail === ''
        ? ''
        : `: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`;
    super(`HTTP ${status}${tail}`);
    this.name = 'ApiError';
  }
}

function headersOf(init: RequestInit | undefined): Record<string, string> {
  return { ...(init?.headers as Record<string, string> | undefined) };
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = headersOf(init);
  const bodyIsForm = init?.body instanceof FormData;
  if (!bodyIsForm && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = await resp.clone().json();
    } catch {
      detail = await resp.text();
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;

  const ct = resp.headers.get('Content-Type') || '';
  if (ct.includes('application/json')) return (await resp.json()) as T;
  return (await resp.text()) as unknown as T;
}

// Returns `null` instead of throwing when the response is a 404.
// Useful for "may not exist yet" reads (env-doc, MCP policy, etc.).
export async function apiRequestOrNull<T>(
  path: string,
  init?: RequestInit,
): Promise<T | null> {
  try {
    return await apiRequest<T>(path, init);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}
