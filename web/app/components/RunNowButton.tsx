"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE =
  typeof window !== "undefined"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type IngestLimits = {
  allowed: boolean;
  daily_limit: number;
  daily_used: number;
  daily_remaining: number;
  min_interval_seconds: number;
  next_allowed_at: string | null;
  server_time?: string;
  timezone?: string;
};

export default function RunNowButton({
  compact = false,
  onCompleted,
  onStatus,
}: {
  compact?: boolean;
  onCompleted?: () => void;
  onStatus?: (status: string, level?: "info" | "success" | "error") => void;
}) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [limits, setLimits] = useState<IngestLimits | null>(null);
  const [serverOffsetMs, setServerOffsetMs] = useState(0);
  const [tick, setTick] = useState(0);
  const router = useRouter();

  const fetchLimits = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/ingest/limits`, {
        cache: "no-store",
      });
      if (!resp.ok) return;
      const data = (await resp.json()) as IngestLimits;
      setLimits(data);
      if (data.server_time) {
        const serverMs = new Date(data.server_time).getTime();
        setServerOffsetMs(serverMs - Date.now());
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    fetchLimits();
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const nowServer = useMemo(() => {
    return new Date(Date.now() + serverOffsetMs);
  }, [serverOffsetMs, tick]);

  const nextAllowedAt = useMemo(() => {
    if (!limits?.next_allowed_at) return null;
    const dt = new Date(limits.next_allowed_at);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }, [limits?.next_allowed_at]);

  const waitSeconds = useMemo(() => {
    if (!nextAllowedAt) return 0;
    const diff = Math.ceil((nextAllowedAt.getTime() - nowServer.getTime()) / 1000);
    return Math.max(0, diff);
  }, [nextAllowedAt, nowServer]);

  const isBlocked = useMemo(() => {
    if (loading) return true;
    if (!limits) return false;
    if (limits.daily_remaining <= 0) return true;
    return waitSeconds > 0;
  }, [limits, waitSeconds, loading]);

  const poll = async (runId: string) => {
    try {
      const resp = await fetch(`${API_BASE}/api/ingest/status/${runId}`);
      const data = await resp.json();
      if (data.status === "completed") {
        setStatus("完成 ✅");
        onStatus?.("完成 ✅", "success");
        setLoading(false);
        fetchLimits();
        onCompleted?.();
        router.refresh();
        return;
      }
      if (data.status === "failed") {
        setStatus("失败，请检查后端日志");
        onStatus?.("失败，请检查后端日志", "error");
        setLoading(false);
        fetchLimits();
        return;
      }
      setStatus(`运行中（${data.status}）`);
      onStatus?.(`运行中（${data.status}）`, "info");
      setTimeout(() => poll(runId), 2000);
    } catch {
      setStatus("状态查询失败");
      onStatus?.("状态查询失败", "error");
      setLoading(false);
      fetchLimits();
    }
  };

  const handleClick = async () => {
    if (isBlocked) {
      if (limits?.daily_remaining === 0) {
        setStatus("今日已达上限");
        onStatus?.("今日已达上限", "error");
      } else if (waitSeconds > 0) {
        setStatus(`请等待 ${waitSeconds} 秒再试`);
        onStatus?.(`请等待 ${waitSeconds} 秒再试`, "info");
      }
      return;
    }
    setLoading(true);
    setStatus("触发中…");
    onStatus?.("触发中…", "info");
    try {
      const resp = await fetch(`${API_BASE}/api/ingest/run`, {
        method: "POST",
      });
      const data = await resp.json();
      if (resp.status === 429) {
        setLoading(false);
        if (data?.limits) {
          setLimits(data.limits);
        }
        setStatus(data?.message || "触发频率过高，请稍后再试");
        onStatus?.(data?.message || "触发频率过高，请稍后再试", "error");
        return;
      }
      if (data.run_id) {
        setStatus("已触发，拉取中…");
        onStatus?.("已触发，拉取中…", "success");
        fetchLimits();
        poll(data.run_id);
      } else {
        setStatus("触发失败");
        onStatus?.("触发失败", "error");
        setLoading(false);
        fetchLimits();
      }
    } catch {
      setStatus("触发失败");
      onStatus?.("触发失败", "error");
      setLoading(false);
      fetchLimits();
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleClick}
        disabled={isBlocked}
        className="px-4 py-2 rounded-full bg-coral-500 text-white font-medium shadow-soft disabled:opacity-60"
      >
        {loading ? "运行中" : "立即抓取"}
      </button>
      {!compact && (
        <div className="text-sm text-ink-600 flex flex-col">
          {status && <span>{status}</span>}
          {limits && (
            <span>
              今日剩余次数 {limits.daily_remaining}/{limits.daily_limit}
              {waitSeconds > 0 ? `，冷却 ${waitSeconds}s` : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
