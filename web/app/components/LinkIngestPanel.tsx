"use client";

import { useState } from "react";

const API_BASE =
  typeof window !== "undefined"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Props = {
  onCompleted?: (id?: number) => void;
  onStatus?: (text: string, level?: "success" | "error" | "info") => void;
};

export default function LinkIngestPanel({ onCompleted, onStatus }: Props) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (loading) return;
    if (!url.trim()) {
      onStatus?.("请输入链接", "info");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ingest/url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!res.ok) {
        throw new Error("ingest_url_failed");
      }
      const data = await res.json();
      onStatus?.("已抓取并入库", "success");
      setUrl("");
      onCompleted?.(data.id);
    } catch {
      onStatus?.("抓取失败，请稍后再试", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-ink-100 bg-white/80 p-4 flex flex-col gap-3">
      <div className="text-sm text-ink-600">
        传入任意链接，系统将抓取并存入「真实世界」库。
      </div>
      <div className="flex flex-col md:flex-row gap-3">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/your-article"
          className="flex-1 rounded-xl border border-ink-200 px-4 py-2"
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={loading}
          className="px-4 py-2 rounded-xl bg-ink-900 text-white"
        >
          {loading ? "抓取中…" : "抓取"}
        </button>
      </div>
    </div>
  );
}
