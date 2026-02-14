"use client";

type SourceItem = {
  id: number;
  name: string;
  type: string;
  items_count?: number;
  active?: boolean;
};

const TYPE_LABELS: Record<string, string> = {
  rss: "RSS / 博客",
  hn: "Hacker News",
  brave: "搜索 / 聚合",
  newsapi: "新闻 API",
  producthunt: "Product Hunt",
};

function groupSources(sources: SourceItem[]) {
  const groups: Record<string, SourceItem[]> = {};
  sources.forEach((source) => {
    const key = TYPE_LABELS[source.type] || "其他";
    if (!groups[key]) groups[key] = [];
    groups[key].push(source);
  });
  return Object.entries(groups);
}

export default function SourceFilter({
  sources,
  activeSource,
  onSelect,
}: {
  sources: SourceItem[];
  activeSource: string | null;
  onSelect: (sourceId: string | null) => void;
}) {
  if (!sources.length) return null;
  const grouped = groupSources(sources);
  return (
    <details className="rounded-2xl border border-ink-100 bg-white/80 p-4">
      <summary className="cursor-pointer text-sm text-ink-700">
        按来源筛选
      </summary>
      <div className="mt-4 flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onSelect(null)}
            className={`px-3 py-1 rounded-full text-sm border transition ${
              !activeSource
                ? "bg-ink-900 text-white border-ink-900"
                : "bg-white/70 text-ink-700 border-ink-300 hover:border-ink-900"
            }`}
          >
            全部来源
          </button>
        </div>
        {grouped.map(([group, items]) => (
          <details key={group} className="rounded-xl bg-cream-50 p-3">
            <summary className="cursor-pointer text-sm text-ink-700">
              {group}（{items.length}）
            </summary>
            <div className="mt-3 flex flex-wrap gap-2">
              {items.map((source) => {
                const isActive = activeSource === String(source.id);
                return (
                  <button
                    key={source.id}
                    type="button"
                    onClick={() => onSelect(String(source.id))}
                    className={`px-3 py-1 rounded-full text-xs border transition ${
                      isActive
                        ? "bg-ink-900 text-white border-ink-900"
                        : "bg-white text-ink-700 border-ink-200 hover:border-ink-900"
                    }`}
                  >
                    {source.name}
                    {typeof source.items_count === "number"
                      ? ` · ${source.items_count}`
                      : ""}
                  </button>
                );
              })}
            </div>
          </details>
        ))}
      </div>
    </details>
  );
}
