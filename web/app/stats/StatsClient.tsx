"use client";

import { useEffect, useState } from "react";

const API_BASE =
  typeof window !== "undefined"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SourceStat = {
  id: number;
  name: string;
  type: string;
  active: boolean;
  weight: number;
  fetch_interval_minutes: number;
  last_fetch_at: string | null;
  items_count: number;
  last_item_at: string | null;
};

type Limits = {
  allowed: boolean;
  daily_limit: number;
  daily_used: number;
  daily_remaining: number;
  min_interval_seconds: number;
  next_allowed_at: string | null;
  server_time: string;
  timezone: string;
};

export default function StatsClient() {
  const [sources, setSources] = useState<SourceStat[]>([]);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const fetchStats = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const [statsRes, limitsRes] = await Promise.all([
        fetch(`${API_BASE}/api/sources/stats`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/ingest/limits`, { cache: "no-store" }),
      ]);
      if (!statsRes.ok) throw new Error("stats_failed");
      const statsData = await statsRes.json();
      setSources(statsData.sources || []);
      if (limitsRes.ok) {
        const limitsData = await limitsRes.json();
        setLimits(limitsData);
      }
    } catch {
      setMessage("统计加载失败，请稍后再试");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const runSource = async (sourceId: number) => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/ingest/source/${sourceId}`, {
        method: "POST",
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        if (
          payload?.error === "ingest_rate_limited" ||
          payload?.error === "ingest_source_rate_limited"
        ) {
          setMessage("触发过于频繁，请稍后再试");
          return;
        }
        throw new Error("run_failed");
      }
      const data = await res.json();
      setMessage(`已触发抓取：${data.run_id}`);
      fetchStats();
    } catch {
      setMessage("触发失败，请稍后重试");
    }
  };

  return (
    <main className="max-w-6xl mx-auto px-4 pt-10 pb-20">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-display text-ink-900">来源统计</h1>
        <button
          type="button"
          onClick={fetchStats}
          className="px-4 py-2 rounded-full bg-ink-900 text-white"
        >
          刷新
        </button>
      </div>

      {limits && (
        <div className="mb-6 text-sm text-ink-600">
          今日剩余条数：{limits.daily_remaining}/{limits.daily_limit}，最小间隔：
          {Math.round(limits.min_interval_seconds / 60)} 分钟
        </div>
      )}

      {message && <div className="mb-4 text-sm text-ink-600">{message}</div>}

      <div className="overflow-auto rounded-2xl border border-ink-100 bg-white/80">
        <table className="min-w-full text-sm">
          <thead className="bg-cream-50 text-ink-700">
            <tr>
              <th className="text-left px-4 py-3">来源</th>
              <th className="text-left px-4 py-3">类型</th>
              <th className="text-right px-4 py-3">条目数</th>
              <th className="text-left px-4 py-3">最近入库</th>
              <th className="text-left px-4 py-3">最近抓取</th>
              <th className="text-left px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.id} className="border-t border-ink-100">
                <td className="px-4 py-3">
                  <div className="font-medium text-ink-900">{source.name}</div>
                  <div className="text-xs text-ink-500">
                    权重 {source.weight} · 间隔 {source.fetch_interval_minutes} 分钟
                  </div>
                </td>
                <td className="px-4 py-3 text-ink-600">{source.type}</td>
                <td className="px-4 py-3 text-right text-ink-800">{source.items_count}</td>
                <td className="px-4 py-3 text-ink-600">{source.last_item_at || "-"}</td>
                <td className="px-4 py-3 text-ink-600">{source.last_fetch_at || "-"}</td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    onClick={() => runSource(source.id)}
                    className="px-3 py-1.5 rounded-full bg-cream-100 text-ink-900"
                    disabled={loading}
                  >
                    只抓这个来源
                  </button>
                </td>
              </tr>
            ))}
            {!sources.length && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-ink-500">
                  {loading ? "加载中..." : "暂无数据"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
