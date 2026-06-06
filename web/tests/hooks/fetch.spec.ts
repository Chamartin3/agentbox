import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useFetch } from '@/hooks/fetch';

describe('useFetch', () => {
  it('starts in loading state, then resolves with data', async () => {
    const loader = vi.fn(async () => 42);
    const { result } = renderHook(() => useFetch(loader));

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBe(42);
    expect(result.current.error).toBeNull();
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it('captures errors and wraps non-Error throws', async () => {
    const loader = vi.fn(async () => {
      throw 'boom';
    });
    const { result } = renderHook(() => useFetch(loader));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('boom');
    expect(result.current.data).toBeNull();
  });

  it('refresh() reloads from the latest loader', async () => {
    let n = 0;
    const loader = vi.fn(async () => ++n);
    const { result } = renderHook(() => useFetch(loader));
    await waitFor(() => expect(result.current.data).toBe(1));

    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.data).toBe(2);
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it('reloads when deps change', async () => {
    const loader = vi.fn(async (id: number) => id * 10);
    const { result, rerender } = renderHook(({ id }) => useFetch(() => loader(id), [id]), {
      initialProps: { id: 1 },
    });
    await waitFor(() => expect(result.current.data).toBe(10));

    rerender({ id: 2 });
    await waitFor(() => expect(result.current.data).toBe(20));
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it('stale-response guard: ignores resolved result from prior in-flight call', async () => {
    // Two pending loaders; resolve second first, then first - first must be discarded.
    let resolveA!: (v: number) => void;
    let resolveB!: (v: number) => void;
    const pA = new Promise<number>((r) => (resolveA = r));
    const pB = new Promise<number>((r) => (resolveB = r));
    const loader = vi
      .fn<[], Promise<number>>()
      .mockImplementationOnce(() => pA)
      .mockImplementationOnce(() => pB);

    const { result } = renderHook(() => useFetch(loader));
    await act(async () => {
      // kick off second call before first resolves
      void result.current.refresh();
    });

    // resolve in reverse order
    resolveB(2);
    await waitFor(() => expect(result.current.data).toBe(2));
    resolveA(1);
    // stale call settles after; data must still reflect latest (2)
    await new Promise((r) => setTimeout(r, 0));
    expect(result.current.data).toBe(2);
  });
});
