"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE =
  typeof window !== "undefined"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Props = {
  itemId: number;
  initialFavorite: boolean;
  initialDisliked: boolean;
};

export default function ItemActions({ itemId, initialFavorite, initialDisliked }: Props) {
  const [favorite, setFavorite] = useState(initialFavorite);
  const [disliked, setDisliked] = useState(initialDisliked);
  const [status, setStatus] = useState<string | null>(null);
  const startRef = useRef<number | null>(null);

  const itemUrl = useMemo(() => `${API_BASE}/api/item/${itemId}`, [itemId]);

  useEffect(() => {
    startRef.current = Date.now();
    fetch(`${itemUrl}/view`, { method: "POST" }).catch(() => null);

    return () => {
      const start = startRef.current;
      if (!start) return;
      const seconds = Math.max(0, Math.round((Date.now() - start) / 1000));
      if (seconds <= 0) return;
      const body = JSON.stringify({ seconds });
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon(`${itemUrl}/read`, blob);
      } else {
        fetch(`${itemUrl}/read`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          keepalive: true,
        }).catch(() => null);
      }
    };
  }, [itemUrl]);

  const toggleFavorite = async () => {
    const next = !favorite;
    setFavorite(next);
    setStatus(next ? "已收藏" : "已取消");
    try {
      await fetch(`${itemUrl}/favorite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ favorite: next }),
      });
    } catch {
      setStatus("操作失败");
      setFavorite(!next);
    }
  };

  const toggleDislike = async () => {
    const next = !disliked;
    setDisliked(next);
    setStatus(next ? "已标记不感兴趣" : "已取消不感兴趣");
    try {
      const res = await fetch(`${itemUrl}/dislike`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ disliked: next }),
      });
      if (!res.ok) {
        throw new Error("request_failed");
      }
      if (next) {
        try {
          window.localStorage.setItem(`disliked:${itemId}`, "1");
        } catch {}
        window.dispatchEvent(
          new CustomEvent("item-disliked", { detail: { id: itemId, disliked: true } })
        );
      }
    } catch {
      setStatus("操作失败");
      setDisliked(!next);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={toggleFavorite}
        className={`px-3 py-1 rounded-full text-sm border transition ${
          favorite
            ? "bg-ink-900 text-white border-ink-900"
            : "bg-white/70 text-ink-700 border-ink-300 hover:border-ink-900"
        }`}
      >
        {favorite ? "已收藏" : "收藏"}
      </button>
      <button
        onClick={toggleDislike}
        className={`px-3 py-1 rounded-full text-sm border transition ${
          disliked
            ? "bg-rose-600 text-white border-rose-600"
            : "bg-white/70 text-ink-700 border-ink-300 hover:border-rose-600"
        }`}
      >
        {disliked ? "取消不感兴趣" : "不感兴趣"}
      </button>
      {status && <span className="text-xs text-ink-600">{status}</span>}
    </div>
  );
}
