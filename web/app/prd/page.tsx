import Link from "next/link";
import type { ReactNode } from "react";

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-3">
      <h2 className="text-2xl font-display text-ink-900">{title}</h2>
      {children}
    </section>
  );
}

export default function PRDPage() {
  return (
    <main className="max-w-5xl mx-auto pt-16 pb-24 md:pt-10">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <span className="text-xs uppercase tracking-[0.3em] text-ink-600">
            Product Requirements Document
          </span>
          <h1 className="text-3xl md:text-4xl font-display text-ink-900">
            ShuiBook 小红书式个人信息流 — PRD
          </h1>
          <p className="text-sm text-ink-600">
            版本日期：2026-02-13（当前系统实现状态快照）
          </p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/" className="text-ink-600">
            返回首页
          </Link>
          <Link href="/admin" className="text-ink-600">
            管理后台
          </Link>
        </div>
      </div>

      <div className="mt-10 space-y-10">
        <Section id="overview" title="1. 产品定位与目标">
          <p className="text-ink-700 leading-relaxed">
            ShuiBook 是一套“单人使用”的小红书式信息流系统，目标是让用户每天在一个移动端
            友好、图文卡片为主的界面里，快速获取自己关心的主题资讯与观点，并能在需要时展开到
            详细中文总结与全文翻译。系统不做社交、不做账号体系，只服务一个人，强调信息密度、
            快速消化与可管理的抓取管道。
          </p>
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>聚焦 9 大兴趣主题：AI效率/项目管理、具身智能/机器人、AI硬件/应用/实验室发布、育儿/婴幼儿、HiFi音频、音乐推荐、宏观经济/时政、极客小玩意、用户体验/分享。</li>
            <li>卡片式瀑布流 + 详情页结构化摘要 + 中文全文翻译。</li>
            <li>两条入口：真实世界（抓取）+ “链接抓取”。</li>
            <li>面向生产环境部署：HTTPS + 计划任务 + 管理后台 + 限频与日志。</li>
          </ul>
        </Section>

        <Section id="scope" title="2. 范围与非目标">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl bg-white/70 p-5 shadow-soft">
              <h3 className="font-display text-lg text-ink-900">已覆盖范围</h3>
              <ul className="mt-3 list-disc pl-5 text-ink-700 leading-relaxed">
                <li>单用户信息流浏览、主题筛选、随机化刷新与懒加载。</li>
                <li>详情页的结构化摘要、全文翻译、元信息、原文链接。</li>
                <li>来源抓取、去重、排序、摘要、翻译、入库。</li>
                <li>自动定时抓取 + 手动触发 + 每来源手动触发。</li>
                <li>收藏/不感兴趣/阅读时长/浏览次数的行为采集。</li>
                <li>OTP 管理后台：来源权重、抓取任务、日志、取消任务。</li>
              </ul>
            </div>
            <div className="rounded-2xl bg-white/70 p-5 shadow-soft">
              <h3 className="font-display text-lg text-ink-900">明确不做</h3>
              <ul className="mt-3 list-disc pl-5 text-ink-700 leading-relaxed">
                <li>多用户系统、注册登录、社交关系、评论/点赞。</li>
                <li>广告、商业化推荐、复杂画像或隐私分析。</li>
                <li>全文版权内容长期存储（只保留摘要/译文/有限节选）。</li>
                <li>专业医疗建议输出（育儿/健康只做信息整理）。</li>
              </ul>
            </div>
          </div>
        </Section>

        <Section id="ux" title="3. 关键体验与信息架构">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>首页瀑布流卡片：图片优先、标题 + 2 行摘要 + 话题标签。</li>
            <li>顶部世界切换：真实世界 / 链接抓取。</li>
            <li>主题标签筛选：9 大主题 + “收藏”。</li>
            <li>移动端固定顶部/底部操作栏：快速首页/收藏/刷新/切换。</li>
            <li>详情页：结构化摘要 + 中文全文翻译 + 讨论总结 + 元信息。</li>
            <li>随机化刷新：每次刷新首屏从最新池中抽取一段，避免重复。</li>
          </ul>
        </Section>

        <Section id="features" title="4. 主要功能清单">
          <div className="space-y-6">
            <div>
              <h3 className="font-display text-lg text-ink-900">4.1 信息流浏览</h3>
              <ul className="mt-2 list-disc pl-5 text-ink-700 leading-relaxed">
                <li>瀑布流卡片，默认 20 条/页，向下滚动自动加载。</li>
                <li>主题筛选 + 世界筛选；收藏=专用过滤。</li>
                <li>支持“随机浏览 / 时间顺序”切换；翻页使用 cursor 稳定分页。</li>
                <li>点击进入详情页；返回保留当前位置。</li>
              </ul>
            </div>
            <div>
              <h3 className="font-display text-lg text-ink-900">4.2 详情页</h3>
              <ul className="mt-2 list-disc pl-5 text-ink-700 leading-relaxed">
                <li>封面图、中文标题、摘要、要点、争议点、可执行建议。</li>
                <li>“发生了什么 / 为什么重要 / 人们怎么看”三段式结构。</li>
                <li>中文全文翻译（按段落保留结构，必要时分块翻译）。</li>
                <li>展示来源、发布时间、抓取时间与“阅读原文”链接。</li>
              </ul>
            </div>
            <div>
              <h3 className="font-display text-lg text-ink-900">4.3 行为与偏好</h3>
              <ul className="mt-2 list-disc pl-5 text-ink-700 leading-relaxed">
                <li>收藏：永久保留，不进入清理流程。</li>
                <li>不感兴趣：立即从列表隐藏，并写入负反馈信号，抑制后续同源/同主题内容。</li>
                <li>阅读行为统计：浏览次数、最后浏览时间、累计阅读秒数、长读次数。</li>
              </ul>
            </div>
            <div>
              <h3 className="font-display text-lg text-ink-900">4.5 链接抓取</h3>
              <ul className="mt-2 list-disc pl-5 text-ink-700 leading-relaxed">
                <li>输入任意 URL，立即抓取并存入“真实世界”。</li>
                <li>仍走同样的去重、摘要、翻译、标签推断流程。</li>
                <li>用于临时补充优质文章或会员内容。</li>
              </ul>
            </div>
          </div>
        </Section>

        <Section id="sources" title="5. 内容来源与抓取策略">
          <p className="text-ink-700 leading-relaxed">
            来源采用可插拔机制，均在 config/sources.yaml 中声明。每个来源包含：name、type、url 或
            query/keywords、topics、fetch_interval_minutes、weight、active。来源会在管理后台展示并可
            在线调整权重/间隔/开关（同时写回 YAML）。
          </p>
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>支持类型：RSS、Hacker News（Algolia 搜索 + Top stories）、Brave Search、NewsAPI、Product Hunt。</li>
            <li>默认覆盖：AI/机器人/硬件、育儿、HiFi、音乐、宏观时政、极客玩具、论坛分享。</li>
            <li>中文社区来源已加入：Linux.do、V2EX 等。</li>
            <li>Medium：RSS + 61 服务器远端浏览器抓取（登录态常驻），限频更严格。</li>
          </ul>
        </Section>

        <Section id="ingest" title="6. 抓取与处理流程（真实世界）">
          <ol className="list-decimal pl-5 text-ink-700 leading-relaxed">
            <li>加载 sources.yaml（仅 active）。</li>
            <li>按来源拉取候选链接；对 scheduled 模式检查 fetch_interval_minutes，避免频繁抓取。</li>
            <li>过滤超过 MAX_ITEM_AGE_DAYS（默认 60 天）的旧内容。</li>
            <li>URL 规范化（canonicalize），并按 URL + 内容哈希双重去重。</li>
            <li>按评分 + 多主题覆盖策略筛选：每主题至少 1 条，HiFi/音乐保障最小占比。</li>
            <li>正文提取：trafilatura 优先，readability-lxml 兜底；失败则 link-only。</li>
            <li>摘要生成：OpenAI 结构化 JSON；育儿内容强制免责声明。</li>
            <li>中文全文翻译：按段落分块翻译，使用较轻量模型（默认 gpt-4o-mini）。</li>
            <li>图片提取：og:image 或正文首图，失败使用占位图；可选下载到 /media。</li>
            <li>写入 Postgres，记录来源、话题、评分、时间、讨论总结。</li>
          </ol>
        </Section>

        <Section id="summary" title="8. 摘要与翻译规范">
          <div className="space-y-4 text-ink-700 leading-relaxed">
            <p>
              摘要输出为严格 JSON，并通过 Pydantic 校验；若 JSON 解析失败会回退解析最外层大括号。摘要长度目标 300-600 字，
              不允许编造。育儿/健康内容要求提供“非医疗建议免责声明”。
            </p>
            <div className="rounded-2xl bg-white/70 p-4 shadow-soft">
              <p className="text-sm text-ink-600">摘要 JSON 字段</p>
              <ul className="mt-2 list-disc pl-5 text-ink-700">
                <li>title_zh, summary_zh</li>
                <li>bullets[], sentiment</li>
                <li>controversy_points[], practical_takeaways[]</li>
                <li>可选：what_happened_zh, why_it_matters_zh, disclaimer_zh</li>
              </ul>
            </div>
            <p>
              全文翻译按段落分块，保留原文结构；原文过短（&lt;80 字）则不翻译。翻译结果缓存到 Redis（默认 72 小时），
              详情页优先读取缓存以减少模型调用；主链路会清理翻译中的大量空行，避免可读性劣化。
            </p>
          </div>
        </Section>

        <Section id="people" title="9. 讨论与“人们怎么看”">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>Hacker News：抓取前 20 条高赞评论并总结“共识 + 分歧”。</li>
            <li>其它来源默认不生成“猜测观点”（ALLOW_SPECULATION=false）。</li>
            <li>讨论摘要保存到 item_discussions，详情页展示为 People’s Takes。</li>
          </ul>
        </Section>

        <Section id="ranking" title="10. 排序与覆盖策略">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>评分 = 来源权重 + 新鲜度（72 小时线性衰减）+ 主题覆盖 + HN 互动。</li>
            <li>引入“不感兴趣”负反馈惩罚：同源/同主题候选会降权，强负反馈可直接抑制入库。</li>
            <li>topic_score 根据候选命中主题数决定。</li>
            <li>筛选阶段保证多主题覆盖，避免单一标签霸屏。</li>
          </ul>
        </Section>

        <Section id="limits" title="11. 限频与容错">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>全局抓取限频：同一 host 默认 30 秒间隔；Medium 更严格。</li>
            <li>手动抓取：全局每天最多 10 条新入库，间隔至少 5 分钟。</li>
            <li>手动单来源抓取：每来源每天最多 10 条新入库，间隔至少 5 分钟。</li>
            <li>计数基于“有效入库条数”，非请求次数。</li>
            <li>失败时记录 run.error 与日志；支持取消任务。</li>
            <li>可选远程抓取：403/429 时通过 SSH 代理抓取（REMOTE_FETCH_*）。</li>
          </ul>
        </Section>

        <Section id="data" title="12. 数据模型">
          <div className="space-y-4 text-ink-700 leading-relaxed">
            <p>核心表结构（Postgres + SQLAlchemy）：</p>
            <ul className="list-disc pl-5">
              <li>sources：name/type/config/topics/weight/fetch_interval_minutes/active/last_fetch_at</li>
              <li>items：url/url_canonical/content_hash/title/summary/translation/image/source/world/ai_meta/score/metrics</li>
              <li>item_topics：item_id + topic（多对多）</li>
              <li>ingest_runs：id/status/mode/candidates/new_items/error/日志</li>
              <li>item_discussions：HN 讨论摘要（共识/分歧）</li>
            </ul>
          </div>
        </Section>

        <Section id="api" title="13. API 设计（核心）">
          <div className="space-y-4 text-ink-700 leading-relaxed">
            <p>公共 API：</p>
            <ul className="list-disc pl-5">
              <li>GET /api/feed?topic=&amp;limit=&amp;cursor=&amp;world=real&amp;order=random|time</li>
              <li>GET /api/item/{`{id}`}</li>
              <li>POST /api/item/{`{id}`}/favorite</li>
              <li>POST /api/item/{`{id}`}/dislike</li>
              <li>POST /api/item/{`{id}`}/view, /read</li>
              <li>POST /api/ingest/run（手动全量）</li>
              <li>POST /api/ingest/url（单链接抓取）</li>
              <li>GET /api/ingest/status/{`{run_id}`}</li>
            </ul>
            <p>管理 API（需 OTP 登录获取 token）：</p>
            <ul className="list-disc pl-5">
              <li>POST /api/admin/login</li>
              <li>GET /api/admin/sources, PATCH /api/admin/source/{`{id}`}</li>
              <li>POST /api/ingest/source/{`{id}`}</li>
              <li>GET /api/admin/ingest/recent, /api/admin/ingest/logs/{`{run_id}`}</li>
              <li>POST /api/admin/ingest/cancel/{`{run_id}`}</li>
            </ul>
          </div>
        </Section>

        <Section id="frontend" title="14. 前端实现与交互">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>Next.js App Router + TailwindCSS + 瀑布流 CSS columns。</li>
            <li>首页：WorldTabs + TopicTabs + RunNow + Masonry 卡片。</li>
            <li>移动端固定顶部/底部：快速切换、刷新、收藏。</li>
            <li>详情页：收藏/不感兴趣/阅读计时、翻译正文展示。</li>
            <li>管理后台：OTP 登录、来源配置、抓取任务、日志。</li>
          </ul>
        </Section>

        <Section id="backend" title="15. 后端架构与组件">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>FastAPI + SQLAlchemy + Alembic + Postgres。</li>
            <li>Celery worker 负责抓取、摘要、翻译、清理任务。</li>
            <li>Celery beat 负责任务调度（4 小时抓取、每日清理）。</li>
            <li>Redis 用于限频、任务节流、翻译缓存。</li>
            <li>HTTP 抓取：尊重 robots.txt + 缓存 + 限频；支持远程拉取兜底。</li>
          </ul>
        </Section>

        <Section id="deployment" title="16. 部署与运维">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>docker-compose 一键启动：api/worker/scheduler/web/postgres/redis/caddy。</li>
            <li>Caddy 自动 TLS：你的域名（例如 your-domain.example），HTTPS 入口。</li>
            <li>日志落盘：/data/logs；媒体缓存 /data/media。</li>
            <li>环境变量集中在 .env；示例在 .env.example。</li>
            <li>发布策略：先 build api/web，再无损重启 api/web，worker/scheduler 持续运行消费任务。</li>
            <li>发布后执行健康检查：/api/feed、/api/ingest/recent、前端 / 与 /prd 页面可用性。</li>
          </ul>
        </Section>

        <Section id="security" title="17. 安全与合规">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>单用户系统，不提供公开注册入口。</li>
            <li>管理后台 OTP + 失败次数限制（IP 与全局双维度）。</li>
            <li>尊重 robots.txt；可调 User-Agent 与抓取间隔。</li>
            <li>不长期保存受版权保护全文，仅保留摘要/译文/有限节选。</li>
          </ul>
        </Section>

        <Section id="tests" title="18. 测试与验收标准">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>URL 规范化、内容去重、摘要 JSON 校验有单元测试。</li>
            <li>手动抓取流程可完整跑通并生成中文摘要 + 翻译。</li>
            <li>收藏/不感兴趣/阅读指标可记录并影响展示。</li>
            <li>管理后台能查看来源数量（今日/总计）、任务状态与日志。</li>
          </ul>
        </Section>

        <Section id="config" title="19. 关键配置速查">
          <div className="space-y-4 text-ink-700 leading-relaxed">
            <p>抓取与模型：</p>
            <ul className="list-disc pl-5">
              <li>OPENAI_API_KEY, OPENAI_MODEL（默认 gpt-5-mini）</li>
              <li>TRANSLATE_MODEL（默认 gpt-4o-mini）</li>
              <li>MAX_ITEM_AGE_DAYS, MAX_ITEMS_PER_RUN, MANUAL_MAX_ITEMS</li>
              <li>RATE_LIMIT_SECONDS, MEDIUM_RATE_LIMIT_SECONDS</li>
              <li>REMOTE_FETCH_ENABLED, REMOTE_FETCH_HOST/USER/PORT/KEY_PATH（Medium 远端浏览器抓取）</li>
            </ul>
            <p>抓取来源：</p>
            <ul className="list-disc pl-5">
              <li>config/sources.yaml：新增/调整来源与权重。</li>
            </ul>
            <p>外部服务：</p>
            <ul className="list-disc pl-5">
              <li>BRAVE_SEARCH_API_KEY, NEWSAPI_KEY, FIRECRAWL_API_KEY</li>
              <li>PRODUCTHUNT_TOKEN + PRODUCTHUNT_KEY + PRODUCTHUNT_SECRET</li>
            </ul>
          </div>
        </Section>

        <Section id="future" title="20. 可选后续迭代（非必须）">
          <ul className="list-disc pl-5 text-ink-700 leading-relaxed">
            <li>将“不感兴趣”细化到关键词/实体级信号，提升垃圾抑制精度。</li>
            <li>更细粒度的主题标签体系与多语言内容。</li>
            <li>更完善的抓取异常告警与来源健康度评分。</li>
          </ul>
        </Section>
      </div>
    </main>
  );
}
