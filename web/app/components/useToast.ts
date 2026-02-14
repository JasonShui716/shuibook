"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type ToastType = "info" | "success" | "error";

export type ToastState = {
  text: string;
  type: ToastType;
};

export function useToast(timeoutMs = 2200) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timerRef = useRef<number | null>(null);

  const clearToast = useCallback(() => {
    setToast(null);
  }, []);

  const showToast = useCallback(
    (text: string, type: ToastType = "info") => {
      setToast({ text, type });
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
      }
      timerRef.current = window.setTimeout(() => {
        setToast(null);
        timerRef.current = null;
      }, timeoutMs);
    },
    [timeoutMs]
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, []);

  return { toast, showToast, clearToast };
}
