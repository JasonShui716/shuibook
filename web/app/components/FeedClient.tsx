"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import RunNowButton from "./RunNowButton";
import TopicTabs from "./TopicTabs";
import Toast from "./Toast";
import { useToast } from "./useToast";
import WorldTabs from "./WorldTabs";
import LinkIngestPanel from "./LinkIngestPanel";
import SourceFilter from "./SourceFilter";

const API_BASE =
  typeof window !== "undefined"
    ? window.location.origin
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type FeedItem = {
  id: number;
  title_zh: string | null;
  summary_zh: string | null;
  excerpt: string | null;
  image_url: string;
  topics: string[];
  source: string | null;
  published_at: string | null;
  fetched_at: string | null;
  is_favorite?: boolean;
};

type SourceItem = {
  id: number;
  name: string;
  type: string;
  items_count?: number;
  active?: boolean;
};

type FeedOrder = "random" | "time";

function readStoredFeedState() {
  if (typeof window === "undefined") {
    return {
      topic: "全部",
      world: "real",
      source: null as string | null,
      search: "",
      order: "random" as FeedOrder,
    };
  }
  try {
    const shouldRestore = window.sessionStorage.getItem("feed:return") === "1";
    if (!shouldRestore) {
      return {
        topic: "全部",
        world: "real",
        source: null as string | null,
        search: "",
        order: "random" as FeedOrder,
      };
    }
    const storedTopic = window.sessionStorage.getItem("feed:last_topic") || "全部";
    const storedWorldRaw = window.sessionStorage.getItem("feed:last_world") || "real";
    const storedWorld = storedWorldRaw === "ai" ? "real" : storedWorldRaw;
    const storedSource = window.sessionStorage.getItem("feed:last_source");
    const storedSearch = window.sessionStorage.getItem("feed:last_search") || "";
    const storedOrderRaw = window.sessionStorage.getItem("feed:last_order") || "random";
    const storedOrder: FeedOrder = storedOrderRaw === "time" ? "time" : "random";
    return {
      topic: storedTopic,
      world: storedWorld,
      source: storedSource,
      search: storedSearch,
      order: storedOrder,
    };
  } catch {
    return {
      topic: "全部",
      world: "real",
      source: null as string | null,
      search: "",
      order: "random" as FeedOrder,
    };
  }
}

export default function FeedClient() {
  const initialState = readStoredFeedState();
  const [world, setWorld] = useState(initialState.world);
  const [topic, setTopic] = useState(initialState.topic);
  const [feedOrder, setFeedOrder] = useState<FeedOrder>(initialState.order);
  const [sourceFilter, setSourceFilter] = useState<string | null>(initialState.source);
  const [searchInput, setSearchInput] = useState(initialState.search);
  const [searchQuery, setSearchQuery] = useState(initialState.search);
  const [items, setItems] = useState<FeedItem[]>([]);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast, showToast } = useToast(2000);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const fetchFeedPage = async (
    selected?: string,
    worldScope?: string,
    pageCursor?: string | null,
    replace?: boolean,
    notify?: boolean
  ) => {
    const params = new URLSearchParams();
    if (selected && selected !== "全部") {
      params.set("topic", selected);
    }
    const effectiveWorld = (worldScope || world) === "link" ? "real" : worldScope || world;
    params.set("world", effectiveWorld);
    if (effectiveWorld === "real" && sourceFilter) {
      params.set("source", sourceFilter);
    }
    if (effectiveWorld === "real") {
      params.set("order", feedOrder);
    }
    if (effectiveWorld === "real" && searchQuery.trim()) {
      params.set("search", searchQuery.trim());
    }
    params.set("limit", "20");
    if (pageCursor) params.set("cursor", pageCursor);
    const url = `${API_BASE}/api/feed?${params.toString()}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      throw new Error("feed_fetch_failed");
    }
    const data = await res.json();
    const nextCursor = data.next_cursor || null;
    setCursor(nextCursor);
    setHasMore(!!nextCursor);
    if (replace) {
      setItems(data.items || []);
    } else {
      setItems((prev) => [...prev, ...(data.items || [])]);
    }
    if (notify) {
      showToast("已刷新", "success");
    }
  };

  const refreshFeed = (notify?: boolean) => {
    setItems([]);
    setCursor(null);
    setHasMore(true);
    setLoading(true);
    setError(null);
    fetchFeedPage(topic, world, null, true, notify)
      .catch(() => {
        setError("加载失败，请稍后再试");
        setItems([]);
        showToast("刷新失败，请稍后再试", "error");
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    refreshFeed(false);
  }, [topic, world, sourceFilter, searchQuery, feedOrder]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.sessionStorage.removeItem("feed:return");
  }, []);

  useEffect(() => {
    if (world !== "real" && world !== "link") return;
    const fetchSources = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sources/stats`, { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        const list = (data.sources || []) as SourceItem[];
        const activeSources = list.filter((s) => s.active !== false);
        activeSources.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
        setSources(activeSources);
      } catch {
        return;
      }
    };
    fetchSources();
  }, [world]);

  useEffect(() => {
    if (!hasMore || loadingMore || loading) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        if (!cursor || loadingMore) return;
        setLoadingMore(true);
        fetchFeedPage(topic, world, cursor, false)
          .catch(() => {
            showToast("加载更多失败，请稍后再试", "error");
          })
          .finally(() => {
            setLoadingMore(false);
          });
      },
      { rootMargin: "200px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [cursor, hasMore, loadingMore, loading, topic, world, showToast]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail as { id?: number } | undefined;
      if (!detail?.id) return;
      setItems((prev) => prev.filter((item) => item.id !== detail.id));
    };
    window.addEventListener("item-disliked", handler as EventListener);
    return () => {
      window.removeEventListener("item-disliked", handler as EventListener);
    };
  }, []);

  const worldLabel = useMemo(() => {
    if (world === "link") return "链接抓取";
    return "真实世界";
  }, [world]);

  const headerText = useMemo(() => {
    if (loading) return "加载中…";
    if (error) return error;
    return `当前展示 ${items.length} 条内容（${worldLabel}）。`;
  }, [loading, error, items.length, worldLabel]);

  return (
    <main className="max-w-6xl mx-auto pt-16 pb-20 md:pt-0 md:pb-0">
      <div className="fixed top-0 inset-x-0 z-40 bg-white/85 backdrop-blur border-b md:hidden">
        <div className="max-w-6xl mx-auto h-14 px-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-sm font-semibold text-ink-900">ShuiBook</div>
            <Link href="/admin" className="text-xs text-ink-600">
              统计
            </Link>
          </div>
          {world === "real" && (
            <RunNowButton
              compact
              onCompleted={() => {
                refreshFeed(true);
              }}
              onStatus={(text, level) => {
                showToast(text, level || "info");
              }}
            />
          )}
        </div>
      </div>

      <section className="flex flex-col gap-6 mb-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex flex-col gap-3">
            <WorldTabs
              active={world}
              onSelect={(next) => {
                setWorld(next);
                setTopic("全部");
                if (next !== "real") {
                  setSourceFilter(null);
                  setSearchInput("");
                  setSearchQuery("");
                }
                if (next === "link") {
                  showToast("已切换到链接抓取", "info");
                } else {
                  showToast("已切换到真实世界", "info");
                }
              }}
            />
            <TopicTabs
              active={topic}
              onSelect={(next) => {
                setTopic(next);
                showToast(`已切换到${next}`, "info");
              }}
            />
            {world === "real" && (
              <div className="flex flex-col gap-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setFeedOrder("random");
                      showToast("已切换随机浏览", "info");
                    }}
                    className={`px-3 py-1.5 rounded-xl text-sm ${
                      feedOrder === "random"
                        ? "bg-ink-900 text-white"
                        : "bg-cream-100 text-ink-800"
                    }`}
                  >
                    随机浏览
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setFeedOrder("time");
                      showToast("已切换时间顺序", "info");
                    }}
                    className={`px-3 py-1.5 rounded-xl text-sm ${
                      feedOrder === "time"
                        ? "bg-ink-900 text-white"
                        : "bg-cream-100 text-ink-800"
                    }`}
                  >
                    时间顺序
                  </button>
                </div>
                <div className="flex flex-col md:flex-row gap-2">
                  <input
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder="站内搜索（标题/摘要）"
                    className="flex-1 rounded-xl border border-ink-200 px-4 py-2 text-sm"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setSearchQuery(searchInput.trim());
                        showToast("已更新搜索条件", "info");
                      }}
                      className="px-4 py-2 rounded-xl bg-ink-900 text-white text-sm"
                    >
                      搜索
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSearchInput("");
                        setSearchQuery("");
                        showToast("已清除搜索", "info");
                      }}
                      className="px-4 py-2 rounded-xl bg-cream-100 text-ink-900 text-sm"
                    >
                      清除
                    </button>
                  </div>
                </div>
                <SourceFilter
                  sources={sources}
                  activeSource={sourceFilter}
                  onSelect={(next) => {
                    setSourceFilter(next);
                    showToast(next ? "已切换来源" : "已清除来源筛选", "info");
                  }}
                />
              </div>
            )}
          </div>
          <div className="hidden md:flex items-center gap-4">
            <Link href="/admin" className="text-sm text-ink-600">
              来源统计
            </Link>
            {world === "real" && (
              <RunNowButton
                onCompleted={() => {
                  refreshFeed(true);
                }}
              />
            )}
          </div>
        </div>
          {world === "link" && (
            <LinkIngestPanel
              onCompleted={() => refreshFeed(true)}
              onStatus={(text, level) => {
                showToast(text, level || "info");
              }}
            />
          )}
        <div className="text-sm text-ink-600">{headerText}</div>
      </section>

      <section className="masonry">
        {items.map((item, idx) => (
          <Link
            key={item.id}
            href={`/item/${item.id}`}
            className="masonry-item block mb-6"
            onClick={() => {
              if (typeof window === "undefined") return;
              try {
                window.sessionStorage.setItem("feed:last_topic", topic);
                window.sessionStorage.setItem("feed:last_world", world);
                if (sourceFilter) {
                  window.sessionStorage.setItem("feed:last_source", sourceFilter);
                } else {
                  window.sessionStorage.removeItem("feed:last_source");
                }
                if (searchQuery) {
                  window.sessionStorage.setItem("feed:last_search", searchQuery);
                } else {
                  window.sessionStorage.removeItem("feed:last_search");
                }
                window.sessionStorage.setItem("feed:last_order", feedOrder);
                window.sessionStorage.setItem("feed:return", "1");
              } catch {
                return;
              }
            }}
          >
            <article className="bg-white/80 backdrop-blur rounded-3xl shadow-soft overflow-hidden fade-in">
              <div className="relative w-full h-56">
                <Image
                  src={item.image_url}
                  alt={item.title_zh || "封面"}
                  fill
                  sizes="(max-width: 768px) 100vw, 33vw"
                  className="object-cover"
                  priority={idx < 3}
                />
              </div>
              <div className="p-5 flex flex-col gap-3">
                <h3 className="font-display text-xl text-ink-900 line-clamp-2">
                  {item.title_zh || "（无标题）"}
                </h3>
                <p className="text-sm text-ink-600 line-clamp-2">
                  {item.excerpt || ""}
                </p>
                <div className="text-xs text-ink-500">
                  来源：{item.source || "未知"}
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {item.topics.map((t) => (
                    <span
                      key={t}
                      className="px-2 py-1 rounded-full bg-cream-100 text-ink-700"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            </article>
          </Link>
        ))}
      </section>

      <div className="mt-6 flex items-center justify-center">
        {hasMore ? (
          <button
            type="button"
            onClick={async () => {
              if (loadingMore || !cursor) return;
              setLoadingMore(true);
              try {
                await fetchFeedPage(topic, world, cursor, false);
              } catch {
                showToast("加载更多失败，请稍后再试", "error");
              } finally {
                setLoadingMore(false);
              }
            }}
            className="px-4 py-2 rounded-full bg-cream-100 text-ink-900"
          >
            {loadingMore ? "加载中…" : "加载更多"}
          </button>
        ) : (
          <span className="text-xs text-ink-500">没有更多内容了</span>
        )}
      </div>
      <div ref={sentinelRef} className="h-1" />

      <div className="fixed bottom-0 inset-x-0 z-40 bg-white/90 backdrop-blur border-t md:hidden">
        <div className="max-w-6xl mx-auto h-16 px-6 flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={() => {
              setTopic("全部");
              showToast("已切换到首页", "info");
            }}
            className="px-3 py-2 rounded-full bg-ink-900 text-white"
          >
            首页
          </button>
          <button
            type="button"
            onClick={() => {
              setTopic("收藏");
              showToast("已切换到收藏", "info");
            }}
            className="px-3 py-2 rounded-full bg-white text-ink-900 border border-ink-300"
          >
            收藏
          </button>
          <button
            type="button"
            onClick={() => refreshFeed(true)}
            className="px-3 py-2 rounded-full bg-cream-100 text-ink-900"
          >
            刷新
          </button>
          <button
            type="button"
            onClick={() => {
              setWorld((prev) => {
                const sequence = ["real", "link"];
                const idx = sequence.indexOf(prev);
                const next = sequence[(idx + 1) % sequence.length];
                setTopic("全部");
                if (next === "link") {
                  showToast("已切换到链接抓取", "info");
                } else {
                  showToast("已切换到真实世界", "info");
                }
                return next;
              });
            }}
            className="px-3 py-2 rounded-full bg-white text-ink-900 border border-ink-300"
          >
            切换
          </button>
        </div>
      </div>
      <Toast toast={toast} />
    </main>
  );
}
