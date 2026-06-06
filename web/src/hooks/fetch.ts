import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';

export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
  refresh: () => Promise<void>;
}

export function useFetch<T>(
  loader: () => Promise<T>,
  deps: ReadonlyArray<unknown> = [],
): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const seq = useRef(0);

  const refresh = useCallback(async () => {
    const my = ++seq.current;
    setLoading(true);
    try {
      const result = await loaderRef.current();
      if (seq.current === my) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (seq.current === my) {
        setError(e instanceof Error ? e : new Error(String(e)));
      }
    } finally {
      if (seq.current === my) setLoading(false);
    }
    // ponytail: stale-response guard via seq counter, no AbortController until a slow endpoint actually needs cancellation
  }, []);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, refresh };
}
