"use client";

import { ToastState } from "./useToast";

export default function Toast({
  toast,
  className = "",
}: {
  toast: ToastState | null;
  className?: string;
}) {
  if (!toast) return null;

  const tone =
    toast.type === "success"
      ? "bg-emerald-600"
      : toast.type === "error"
      ? "bg-rose-600"
      : "bg-ink-900";

  return (
    <div
      className={`fixed left-1/2 -translate-x-1/2 bottom-20 md:bottom-8 z-50 ${className}`}
    >
      <div className={`px-4 py-2 rounded-full text-sm text-white shadow-soft ${tone}`}>
        {toast.text}
      </div>
    </div>
  );
}
