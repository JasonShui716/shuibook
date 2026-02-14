import Image from "next/image";
import Link from "next/link";
import ItemActions from "./ItemActions";
import DetailMobileBar from "./DetailMobileBar";

const API_BASE =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

async function fetchItem(id: string) {
  const res = await fetch(`${API_BASE}/api/item/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return null;
  }
  return res.json();
}

export default async function ItemPage({ params }: { params: { id: string } }) {
  const item = await fetchItem(params.id);
  if (!item) {
    return (
      <div className="max-w-4xl mx-auto">
        <p className="text-ink-600">内容不存在。</p>
      </div>
    );
  }

  return (
    <main className="max-w-4xl mx-auto pt-4 pb-20 md:pb-0">
      <Link href="/" className="text-sm text-ink-600">
        ← 返回信息流
      </Link>
      <div className="mt-6 bg-white/80 backdrop-blur rounded-3xl shadow-soft overflow-hidden">
        <div className="relative w-full h-80">
          <Image
            src={item.image_url}
            alt={item.title_zh || "封面"}
            fill
            sizes="100vw"
            className="object-cover"
          />
        </div>
        <div className="p-8 flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h2 className="text-3xl font-display text-ink-900">
              {item.title_zh || "（无标题）"}
            </h2>
            <ItemActions
              itemId={item.id}
              initialFavorite={!!item.is_favorite}
              initialDisliked={!!item.is_disliked}
            />
            <div className="text-xs text-ink-600">
              {`来源：${item.source || "未知"} · 发布：${item.published_at || "未知"} · 抓取：${item.fetched_at}`}
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              {item.topics.map((t: string) => (
                <span key={t} className="px-2 py-1 rounded-full bg-cream-100 text-ink-700">
                  {t}
                </span>
              ))}
            </div>
          </div>

          <section className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-ink-900">发生了什么</h3>
              <p className="text-ink-700 leading-relaxed">
                {item.what_happened_zh || item.summary_zh}
              </p>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-ink-900">为什么重要</h3>
              <p className="text-ink-700 leading-relaxed">
                {item.why_it_matters_zh || item.summary_zh}
              </p>
            </div>
            {item.people_takes && (
              <div>
                <h3 className="text-lg font-semibold text-ink-900">人们的看法</h3>
                <p className="text-ink-700 whitespace-pre-line leading-relaxed">
                  {item.people_takes}
                </p>
              </div>
            )}
          </section>

          <section className="space-y-2">
            <h3 className="text-lg font-semibold text-ink-900">摘要</h3>
            <p className="text-ink-700 leading-relaxed whitespace-pre-line">
              {item.summary_zh}
            </p>
            {item.disclaimer_zh && (
              <p className="text-sm text-ink-600">{item.disclaimer_zh}</p>
            )}
          </section>

          <section className="space-y-2">
            <h3 className="text-lg font-semibold text-ink-900">全文翻译</h3>
            {item.translation_zh ? (
              <details open className="rounded-2xl bg-cream-50 p-4">
                <summary className="cursor-pointer text-sm text-ink-600">
                  {item.translation_is_full ? "展开全文翻译" : "展开（仅部分翻译）"}
                </summary>
                <p className="mt-3 text-ink-700 leading-relaxed whitespace-pre-line">
                  {item.translation_zh}
                </p>
              </details>
            ) : (
              <p className="text-sm text-ink-600">暂无翻译内容。</p>
            )}
          </section>

          <section>
            <h3 className="text-lg font-semibold text-ink-900">实用要点</h3>
            <ul className="list-disc list-inside text-ink-700">
              {(item.practical_takeaways || []).map((p: string) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </section>

          {item.read_original && (
            <div className="text-sm text-ink-600">
              <a
                href={item.read_original}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                阅读原文
              </a>
            </div>
          )}
        </div>
      </div>
      <DetailMobileBar readOriginal={item.read_original} />
    </main>
  );
}
