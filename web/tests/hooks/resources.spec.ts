import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

vi.mock('@/api/repo', () => ({
  repoApi: {
    list: vi.fn(),
    get: vi.fn(),
    versions: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    uploadVersion: vi.fn(),
    uploadZip: vi.fn(),
    uploadSchema: vi.fn(),
    uploadScript: vi.fn(),
    publish: vi.fn(),
    rollback: vi.fn(),
    render: vi.fn(),
    blob: vi.fn(),
    tree: vi.fn(),
    remove: vi.fn(),
    exportPydantic: vi.fn(),
    exportZipUrl: vi.fn(() => '/zip'),
    validateScript: vi.fn(),
  },
}));

import { repoApi } from '@/api/repo';
import {
  useResource,
  useResourceActions,
  useResourceList,
  useResourceVersions,
} from '@/hooks/resources';

const r = repoApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe('resources hooks', () => {
  beforeEach(() => {
    Object.values(r).forEach((m) => {
      if (typeof m.mockReset === 'function') m.mockReset();
    });
  });

  describe('useResource', () => {
    it('returns null when id missing', async () => {
      const { result } = renderHook(() => useResource(null));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(r.get).not.toHaveBeenCalled();
      expect(result.current.data).toBeNull();
    });

    it('bundles detail + versions + rendered text', async () => {
      r.get.mockResolvedValue({
        resource: { id: 'res1' },
        active_version: { id: 'v1' },
      });
      r.versions.mockResolvedValue({ items: [{ id: 'v1' }, { id: 'v2' }] });
      r.render.mockResolvedValue({ text: 'hello' });

      const { result } = renderHook(() => useResource('res1'));
      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.data).toEqual({
        resource: { id: 'res1' },
        activeVersion: { id: 'v1' },
        versions: [{ id: 'v1' }, { id: 'v2' }],
        rendered: 'hello',
      });
      expect(r.render).toHaveBeenCalledWith('res1', 'v1');
    });

    it('skips render call when no active version', async () => {
      r.get.mockResolvedValue({ resource: { id: 'r2' }, active_version: null });
      r.versions.mockResolvedValue({ items: [] });

      const { result } = renderHook(() => useResource('r2'));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(r.render).not.toHaveBeenCalled();
      expect(result.current.data?.rendered).toBe('');
    });

    it('swallows render errors and returns empty rendered', async () => {
      r.get.mockResolvedValue({ resource: { id: 'r3' }, active_version: { id: 'v1' } });
      r.versions.mockResolvedValue({ items: [] });
      r.render.mockRejectedValue(new Error('nope'));

      const { result } = renderHook(() => useResource('r3'));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data?.rendered).toBe('');
      expect(result.current.error).toBeNull();
    });
  });

  describe('useResourceList', () => {
    it('forwards params to repoApi.list', async () => {
      r.list.mockResolvedValue({ items: [] });
      renderHook(() => useResourceList({ q: 'foo', limit: 5 }));
      await waitFor(() =>
        expect(r.list).toHaveBeenCalledWith({ q: 'foo', limit: 5 }),
      );
    });
  });

  describe('useResourceVersions', () => {
    it('returns [] when id absent', async () => {
      const { result } = renderHook(() => useResourceVersions(null));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(r.versions).not.toHaveBeenCalled();
      expect(result.current.data).toEqual([]);
    });

    it('unwraps items[] on success', async () => {
      r.versions.mockResolvedValue({ items: [{ id: 'v1' }] });
      const { result } = renderHook(() => useResourceVersions('r1'));
      await waitFor(() => expect(result.current.data).toEqual([{ id: 'v1' }]));
    });
  });

  describe('useResourceActions', () => {
    it('exposes a stable surface of repoApi methods', () => {
      const { result, rerender } = renderHook(() => useResourceActions());
      const a1 = result.current;
      rerender();
      expect(result.current).toBe(a1);
      expect(typeof a1.list).toBe('function');
      expect(typeof a1.create).toBe('function');
      expect(typeof a1.exportZipUrl).toBe('function');
    });
  });
});
