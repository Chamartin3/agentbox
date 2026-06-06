import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useToast } from '@/hooks/toast';

describe('useToast', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts with no toast', () => {
    const { result } = renderHook(() => useToast());
    expect(result.current.toast).toBeNull();
  });

  it.each([
    ['ok', 'saved'],
    ['error', 'nope'],
  ] as const)('flash(%s) sets a toast', (kind, msg) => {
    const { result } = renderHook(() => useToast());
    act(() => result.current.flash(kind, msg));
    expect(result.current.toast).toEqual({ kind, msg });
  });

  it('auto-dismisses after the configured timeout', () => {
    const { result } = renderHook(() => useToast(1000));
    act(() => result.current.flash('ok', 'hi'));
    expect(result.current.toast).not.toBeNull();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.toast).toBeNull();
  });

  it('dismiss() clears immediately and cancels the timer', () => {
    const { result } = renderHook(() => useToast(5000));
    act(() => result.current.flash('ok', 'hi'));
    act(() => result.current.dismiss());
    expect(result.current.toast).toBeNull();
    // verify timer was cleared (advancing past timeout should not flip state back)
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(result.current.toast).toBeNull();
  });

  it('successive flashes reset the timer', () => {
    const { result } = renderHook(() => useToast(1000));
    act(() => result.current.flash('ok', 'first'));
    act(() => {
      vi.advanceTimersByTime(800);
    });
    act(() => result.current.flash('error', 'second'));
    act(() => {
      vi.advanceTimersByTime(800);
    });
    expect(result.current.toast).toEqual({ kind: 'error', msg: 'second' });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(result.current.toast).toBeNull();
  });
});
