"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Toast from "../components/Toast";
import { useToast } from "../components/useToast";
import ConfirmDialog from "../components/ConfirmDialog";

const API_BASE =
  typeof window !== "undefined"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "shuibook_admin_token";
const TOKEN_EXPIRES_KEY = "shuibook_admin_expires";

type Source = {
  id: number;
  name: string;
  type: string;
  active: boolean;
  weight: number;
  fetch_interval_minutes: number;
  last_fetch_at: string | null;
  topics: string[];
  config: Record<string, unknown>;
  items_count?: number;
  items_today?: number;
  last_item_at?: string | null;
};

type Run = {
  run_id: string;
  mode: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested_at?: string | null;
  canceled_at?: string | null;
  celery_task_id?: string | null;
  total_candidates: number;
  new_items: number;
  error: string | null;
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

export default function AdminClient() {
  const [token, setToken] = useState<string | null>(null);
  const [otp, setOtp] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [runCursor, setRunCursor] = useState<string | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [logRunId, setLogRunId] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [logLoading, setLogLoading] = useState(false);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { toast, showToast } = useToast(2200);
  const [confirm, setConfirm] = useState<{
    title: string;
    description?: string;
    onConfirm: () => void;
  } | null>(null);

  const authHeaders = useMemo(() => {
    const headers = new Headers();
    if (token) headers.set("X-Admin-Token", token);
    return headers;
  }, [token]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (token) return;
    const saved = window.localStorage.getItem(TOKEN_KEY);
    const expiresAt = window.localStorage.getItem(TOKEN_EXPIRES_KEY);
    if (!saved || !expiresAt) return;
    const expiresMs = new Date(expiresAt).getTime();
    if (Number.isNaN(expiresMs) || Date.now() >= expiresMs) {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(TOKEN_EXPIRES_KEY);
      return;
    }
    setToken(saved);
  }, [token]);

  const fetchRuns = async (cursor?: string, append?: boolean) => {
    if (!token) return;
    setRunLoading(true);
    try {
      const url = new URL(`${API_BASE}/api/admin/ingest/recent`);
      url.searchParams.set("limit", "20");
      if (cursor) url.searchParams.set("cursor", cursor);
      const runsRes = await fetch(url.toString(), {
        headers: authHeaders,
        cache: "no-store",
      });
      if (runsRes.status === 401) {
        setToken(null);
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(TOKEN_EXPIRES_KEY);
        setMessage("请重新进行 OTP 验证");
        return;
      }
      if (!runsRes.ok) throw new Error("runs_failed");
      const runsData = await runsRes.json();
      setRuns((prev) => (append ? [...prev, ...(runsData.runs || [])] : runsData.runs || []));
      setRunCursor(runsData.next_cursor || null);
    } catch {
      setMessage("加载失败，请稍后再试");
      showToast("加载失败，请稍后再试", "error");
    } finally {
      setRunLoading(false);
    }
  };

  const fetchAll = async () => {
    if (!token) return;
    setLoading(true);
    setMessage(null);
    try {
      const [sourcesRes, limitsRes] = await Promise.all([
        fetch(`${API_BASE}/api/admin/sources`, {
          headers: authHeaders,
          cache: "no-store",
        }),
        fetch(`${API_BASE}/api/ingest/limits`, { cache: "no-store" }),
      ]);

      if (sourcesRes.status === 401) {
        setToken(null);
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(TOKEN_EXPIRES_KEY);
        setMessage("请重新进行 OTP 验证");
        return;
      }
      if (!sourcesRes.ok) throw new Error("sources_failed");

      const sourcesData = await sourcesRes.json();
      setSources(sourcesData.sources || []);
      await fetchRuns();

      if (limitsRes.ok) {
        const limitsData = await limitsRes.json();
        setLimits(limitsData);
      }
      showToast("已刷新", "success");
    } catch {
      setMessage("加载失败，请稍后再试");
      showToast("加载失败，请稍后再试", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, [token]);

  const handleLogin = async () => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: otp.trim() }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          const data = await res.json().catch(() => ({}));
          const waitSeconds = Number(data?.retry_after_seconds || 0);
          setMessage(
            waitSeconds > 0
              ? `尝试过多，请在 ${Math.ceil(waitSeconds / 60)} 分钟后再试`
              : "尝试过多，请稍后再试"
          );
          showToast("尝试过多，请稍后再试", "error");
          return;
        }
        setMessage("OTP 无效或已过期");
        showToast("OTP 无效或已过期", "error");
        return;
      }
      const data = await res.json();
      if (data?.token) {
        window.localStorage.setItem(TOKEN_KEY, data.token);
      }
      if (data?.expires_at) {
        window.localStorage.setItem(TOKEN_EXPIRES_KEY, data.expires_at);
      }
      setToken(data.token);
      setOtp("");
      setMessage("验证成功");
      showToast("验证成功", "success");
    } catch {
      setMessage("验证失败，请稍后再试");
      showToast("验证失败，请稍后再试", "error");
    }
  };

  const updateSource = async (source: Source) => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/source/${source.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({
          weight: source.weight,
          fetch_interval_minutes: source.fetch_interval_minutes,
          active: source.active,
        }),
      });
      if (!res.ok) {
        throw new Error("update_failed");
      }
      setMessage(`已更新 ${source.name}`);
      showToast(`已更新 ${source.name}`, "success");
      fetchAll();
    } catch {
      setMessage("更新失败，请稍后再试");
      showToast("更新失败，请稍后再试", "error");
    }
  };

  const runSource = async (sourceId: number) => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/ingest/source/${sourceId}`, {
        method: "POST",
        headers: authHeaders,
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        if (
          payload?.error === "ingest_rate_limited" ||
          payload?.error === "ingest_source_rate_limited"
        ) {
          setMessage("触发过于频繁，请稍后再试");
          showToast("触发过于频繁，请稍后再试", "error");
          return;
        }
        throw new Error("run_failed");
      }
      const data = await res.json();
      setMessage(`已触发抓取：${data.run_id}`);
      showToast("已触发抓取", "success");
      fetchAll();
    } catch {
      setMessage("触发失败，请稍后重试");
      showToast("触发失败，请稍后重试", "error");
    }
  };

  const cancelRun = async (runId: string) => {
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/ingest/cancel/${runId}`, {
        method: "POST",
        headers: authHeaders,
      });
      if (res.status === 401) {
        setToken(null);
        window.localStorage.removeItem(TOKEN_KEY);
        window.localStorage.removeItem(TOKEN_EXPIRES_KEY);
        setMessage("请重新进行 OTP 验证");
        return;
      }
      if (!res.ok) {
        throw new Error("cancel_failed");
      }
      const data = await res.json();
      setMessage(`已请求取消：${data.run_id}`);
      showToast("已请求取消", "success");
      fetchAll();
    } catch {
      setMessage("取消失败，请稍后重试");
      showToast("取消失败，请稍后重试", "error");
    }
  };

  const openLog = async (runId: string) => {
    setLogOpen(true);
    setLogRunId(runId);
    setLogLoading(true);
    try {
      const url = `${API_BASE}/api/admin/ingest/logs/${runId}?tail=200`;
      const res = await fetch(url, { headers: authHeaders, cache: "no-store" });
      if (!res.ok) {
        throw new Error("log_failed");
      }
      const data = await res.json();
      setLogLines(data.lines || []);
    } catch {
      setLogLines(["日志加载失败，请稍后再试。"]);
    } finally {
      setLogLoading(false);
    }
  };

  const confirmRunSource = (source: Source) => {
    setConfirm({
      title: "确认抓取该来源？",
      description: `将立即触发一次抓取：${source.name}`,
      onConfirm: () => {
        setConfirm(null);
        runSource(source.id);
      },
    });
  };

  const confirmCancelRun = (runId: string) => {
    setConfirm({
      title: "确认取消该任务？",
      description: `取消任务：${runId}`,
      onConfirm: () => {
        setConfirm(null);
        cancelRun(runId);
      },
    });
  };

  if (!token) {
    return (
      <main className="max-w-md mx-auto px-6 pt-24 pb-20">
        <h1 className="text-2xl font-display text-ink-900 mb-4">管理后台</h1>
        <p className="text-sm text-ink-600 mb-6">输入你的 OTP（6 位动态码）</p>
        <div className="flex gap-3">
          <input
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            placeholder="123456"
            className="flex-1 rounded-xl border border-ink-200 px-4 py-2 text-lg tracking-widest"
          />
          <button
            type="button"
            onClick={handleLogin}
            className="px-4 py-2 rounded-xl bg-ink-900 text-white"
          >
            验证
          </button>
        </div>
        {message && <div className="mt-4 text-sm text-ink-600">{message}</div>}
      </main>
    );
  }

  return (
    <main className="max-w-6xl mx-auto px-4 pt-10 pb-20">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-display text-ink-900">管理后台</h1>
          <p className="text-sm text-ink-600">来源配置、抓取状态与手动触发</p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/" className="px-4 py-2 rounded-full bg-cream-100 text-ink-900">
            返回主页
          </Link>
          <button
            type="button"
            onClick={fetchAll}
            className="px-4 py-2 rounded-full bg-ink-900 text-white"
          >
            刷新
          </button>
          <button
            type="button"
            onClick={() => {
              setToken(null);
              window.localStorage.removeItem(TOKEN_KEY);
              window.localStorage.removeItem(TOKEN_EXPIRES_KEY);
              showToast("已退出", "info");
            }}
            className="px-4 py-2 rounded-full bg-cream-100 text-ink-900"
          >
            退出
          </button>
        </div>
      </div>

      {limits && (
        <div className="mb-6 text-sm text-ink-600">
          今日剩余触发次数：{limits.daily_remaining}/{limits.daily_limit}，最小间隔：
          {Math.round(limits.min_interval_seconds / 60)} 分钟
        </div>
      )}

      {message && <div className="mb-4 text-sm text-ink-600">{message}</div>}

      <section className="mb-10">
        <h2 className="text-lg font-semibold text-ink-900 mb-3">来源配置</h2>
        <div className="overflow-auto rounded-2xl border border-ink-100 bg-white/80">
          <table className="min-w-full text-sm">
            <thead className="bg-cream-50 text-ink-700">
              <tr>
                <th className="text-left px-4 py-3">来源</th>
                <th className="text-left px-4 py-3">类型</th>
                <th className="text-left px-4 py-3">条数(今日/总计)</th>
                <th className="text-left px-4 py-3">权重</th>
                <th className="text-left px-4 py-3">间隔(分钟)</th>
                <th className="text-left px-4 py-3">启用</th>
                <th className="text-left px-4 py-3">最近抓取</th>
                <th className="text-left px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source, idx) => (
                <tr key={source.id} className="border-t border-ink-100">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink-900">{source.name}</div>
                    <div className="text-xs text-ink-500">{source.topics?.join(" / ")}</div>
                  </td>
                  <td className="px-4 py-3 text-ink-600">{source.type}</td>
                  <td className="px-4 py-3 text-ink-700">
                    {(source.items_today ?? 0).toLocaleString()} /{" "}
                    {(source.items_count ?? 0).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="number"
                      step="0.1"
                      value={source.weight}
                      onChange={(e) => {
                        const value = Number(e.target.value || 0);
                        setSources((prev) =>
                          prev.map((s, i) => (i === idx ? { ...s, weight: value } : s))
                        );
                      }}
                      className="w-20 rounded-lg border border-ink-200 px-2 py-1"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="number"
                      value={source.fetch_interval_minutes}
                      onChange={(e) => {
                        const value = Number(e.target.value || 0);
                        setSources((prev) =>
                          prev.map((s, i) =>
                            i === idx ? { ...s, fetch_interval_minutes: value } : s
                          )
                        );
                      }}
                      className="w-24 rounded-lg border border-ink-200 px-2 py-1"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={source.active}
                      onChange={(e) => {
                        const value = e.target.checked;
                        setSources((prev) =>
                          prev.map((s, i) => (i === idx ? { ...s, active: value } : s))
                        );
                      }}
                    />
                  </td>
                  <td className="px-4 py-3 text-ink-600">{source.last_fetch_at || "-"}</td>
                  <td className="px-4 py-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => updateSource(source)}
                      className="px-3 py-1.5 rounded-full bg-cream-100 text-ink-900"
                      disabled={loading}
                    >
                      保存
                    </button>
                    <button
                      type="button"
                      onClick={() => confirmRunSource(source)}
                      className="px-3 py-1.5 rounded-full bg-ink-900 text-white"
                      disabled={loading}
                    >
                      只抓这个来源
                    </button>
                  </td>
                </tr>
              ))}
              {!sources.length && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-ink-500">
                    {loading ? "加载中..." : "暂无数据"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-ink-900 mb-3">抓取任务状态</h2>
        <div className="overflow-auto rounded-2xl border border-ink-100 bg-white/80">
          <table className="min-w-full text-sm">
            <thead className="bg-cream-50 text-ink-700">
              <tr>
                <th className="text-left px-4 py-3">Run ID</th>
                <th className="text-left px-4 py-3">模式</th>
                <th className="text-left px-4 py-3">状态</th>
                <th className="text-left px-4 py-3">开始</th>
                <th className="text-left px-4 py-3">完成</th>
                <th className="text-right px-4 py-3">候选</th>
                <th className="text-right px-4 py-3">新增</th>
                <th className="text-left px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id} className="border-t border-ink-100">
                  <td className="px-4 py-3 text-xs text-ink-600">{run.run_id}</td>
                  <td className="px-4 py-3 text-ink-600">{run.mode}</td>
                  <td className="px-4 py-3 text-ink-600">{run.status}</td>
                  <td className="px-4 py-3 text-ink-600">{run.started_at || "-"}</td>
                  <td className="px-4 py-3 text-ink-600">{run.finished_at || "-"}</td>
                  <td className="px-4 py-3 text-right text-ink-800">
                    {run.total_candidates}
                  </td>
                  <td className="px-4 py-3 text-right text-ink-800">{run.new_items}</td>
                  <td className="px-4 py-3">
                    {["queued", "running"].includes(run.status) ? (
                      <button
                        type="button"
                        onClick={() => confirmCancelRun(run.run_id)}
                        className="px-3 py-1.5 rounded-full bg-cream-100 text-ink-900"
                        disabled={loading}
                      >
                        取消
                      </button>
                    ) : run.status === "cancel_requested" ? (
                      <span className="text-xs text-ink-500">取消中…</span>
                    ) : (
                      <span className="text-xs text-ink-500">-</span>
                    )}
                    <button
                      type="button"
                      onClick={() => openLog(run.run_id)}
                      className="ml-2 px-3 py-1.5 rounded-full bg-white text-ink-700 border border-ink-200"
                    >
                      日志
                    </button>
                  </td>
                </tr>
              ))}
              {!runs.length && (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-ink-500">
                    {loading ? "加载中..." : "暂无记录"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {runCursor && (
          <div className="mt-4 flex justify-center">
            <button
              type="button"
              onClick={() => fetchRuns(runCursor, true)}
              className="px-4 py-2 rounded-full bg-cream-100 text-ink-900"
              disabled={runLoading}
            >
              {runLoading ? "加载中…" : "加载更多"}
            </button>
          </div>
        )}
      </section>
      <Toast toast={toast} className="bottom-auto top-20 md:top-8" />
      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title || ""}
        description={confirm?.description}
        onCancel={() => setConfirm(null)}
        onConfirm={() => confirm?.onConfirm()}
      />
      {logOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
          <div className="w-full max-w-3xl rounded-2xl bg-white shadow-soft p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-lg font-semibold text-ink-900">抓取日志</div>
                <div className="text-xs text-ink-600">{logRunId}</div>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => logRunId && openLog(logRunId)}
                  className="px-3 py-1.5 rounded-full bg-cream-100 text-ink-900"
                >
                  刷新
                </button>
                <button
                  type="button"
                  onClick={() => setLogOpen(false)}
                  className="px-3 py-1.5 rounded-full bg-ink-900 text-white"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="mt-4 max-h-[50vh] overflow-auto rounded-xl bg-ink-50 p-4 text-xs text-ink-700 whitespace-pre-wrap">
              {logLoading ? "加载中…" : logLines.join("\n") || "暂无日志"}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
