import { useCallback, useEffect, useRef, useState } from 'react';

export type ToastKind = 'ok' | 'error';
export type ToastState = { kind: ToastKind; msg: string } | null;

export function useToast(autoDismissMs = 3500) {
  const [toast, setToast] = useState<ToastState>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setToast(null);
  }, []);

  const flash = useCallback(
    (kind: ToastKind, msg: string) => {
      if (timer.current) clearTimeout(timer.current);
      setToast({ kind, msg });
      timer.current = setTimeout(() => setToast(null), autoDismissMs);
    },
    [autoDismissMs],
  );

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return { toast, flash, dismiss };
}
