# Shuibook 小红书式信息流（单用户）

一个个人化信息流：图片卡片 + 中文摘要，支持手动与定时采集。后端 FastAPI + Celery + Postgres，前端 Next.js + Tailwind。

## 功能概览
- 信息流卡片（图片优先 + 2 行摘要）
- 信息流支持两种浏览模式：`随机浏览` / `时间顺序`
- 详情页：中文摘要（300-600 字）+ 发生了什么 / 为什么重要 / 人们的看法
- HN 评论观点提炼（如有）
- 收藏与阅读时长统计（用于后续优化推荐）
- 不感兴趣反馈会抑制后续同源/同主题内容（不仅是隐藏当前卡片）
- URL 规范化 + 内容哈希去重
- 定时采集（每 4 小时，Asia/Singapore）+ 手动触发
- 自动清理：未收藏内容 5 天后删除

## 前置条件
- Docker + Docker Compose
- OpenAI API Key（用于中文摘要）

## 环境变量
复制 `.env.example` 为 `.env` 并填写：
```bash
cp .env.example .env
```

关键变量：
- `OPENAI_API_KEY`：必填
- `OPENAI_MODEL`：默认 `gpt-5-mini`
- `API_BASE_URL`：对外可访问的 API 根地址（用于图片/占位图），例如 `https://your-domain.example`
- `NEXT_PUBLIC_API_URL`：前端访问后端的公网地址（例如 `https://your-domain.example`）
- `API_INTERNAL_URL`：容器内部访问后端（默认 `http://api:8000`）
- `TRANSLATE_FULLTEXT`：是否开启全文翻译（默认 true）
- `TRANSLATE_MODEL`：翻译模型（默认 `gpt-4o-mini`）
- `TRANSLATION_CHUNK_CHARS`：长文分块翻译的字符数（默认 1200）
- `TRANSLATION_TTL_HOURS`：全文翻译缓存保留时长（小时，默认 72）
- 翻译主链路会自动清理模型输出中的大量空行，保证详情页可读性
- `RETENTION_DAYS`：未收藏内容保留天数（默认 5）
- `MAX_ITEM_AGE_DAYS`：采集内容的最老发布日期（默认 60 天）
- `STRICT_SIGNAL_FILTER`：启用高信号严格过滤（默认 true，建议开启）
- `FILTER_FORUM_SOURCES`：过滤论坛类 URL（默认 true，减少低信息密度条目）
- `SCHEDULED_MAX_ITEMS`：定时任务每轮最多入库条数（默认 30，降低噪音与 429 压力）
- `MEDIUM_RATE_LIMIT_SECONDS`：Medium 域名额外限速（默认 3.0 秒）

可选变量（按需）：
- `FIRECRAWL_API_KEY`：当本地抽取失败时，使用 Firecrawl 作为抽取后备
- `BRAVE_SEARCH_API_KEY` / `NEWSAPI_KEY`：可选搜索来源
- `PRODUCTHUNT_TOKEN`：Product Hunt 已有 token
- `PH_KEY` + `PH_SECRET`：Product Hunt OAuth client credentials（系统会自动换取 token）
- `REMOTE_FETCH_ENABLED`：启用远端浏览器抓取（Medium 标准链路；其它域名作为 403/429 后备）
- `REMOTE_FETCH_HOST`/`REMOTE_FETCH_USER`/`REMOTE_FETCH_PORT`：远端 SSH 连接信息
- `REMOTE_FETCH_KEY_PATH`：容器内私钥路径（默认 `/root/.ssh/id_remote_fetch`）

## Medium / 社区源说明
- Medium 通过官方 RSS 获取；部分内容可能有付费墙，抽取失败时将退化为摘要或“链接型”条目。
- Medium 正文抓取统一走“61 服务器远端浏览器登录态”方案（Chromium + CDP + Playwright），避免本机/容器直抓触发 Cloudflare/付费墙。
  - 在 `.env` 设置：`REMOTE_FETCH_ENABLED=true`、`REMOTE_FETCH_HOST/USER/PORT/KEY_PATH`
  - 61 服务器上需要常驻一套带登录态的 Chromium（可用 noVNC 维持），并监听本机 `127.0.0.1:9222`（CDP）
  - 如需把远端 storageState 导出到本仓库（用于排查/备份）：`python3 scripts/medium_save_storage.py`（它会从远端 CDP 导出，不会在本机跑浏览器）
- Linux.do / V2EX 采用 RSS；若遇到访问限制，可在 `sources.yaml` 里临时禁用或降低权重。

## 启动
```bash
docker compose up -d --build
```

> 如果 3000/5432 端口被占用，已在 compose 内将 Web 端口映射为 3010。

## 部署策略（最小中断）
推荐线上发布流程：
1. `git pull` 后仅重建变更服务：`docker compose up -d --build api web`。
2. 保持 `worker/scheduler/postgres/redis` 常驻，避免中断正在执行的抓取任务。
3. 若涉及模型或抓取策略变更，发布后手动跑一次小批量验证：
   - `curl https://your-domain.example/api/feed?limit=3&order=time`
   - `curl https://your-domain.example/api/feed?limit=3&order=random`
4. 观察 `docker compose logs --tail=100 api worker`，确认无持续报错或速率限制风暴。
5. 如需执行集中垃圾清理，优先先 `--dry-run`，再正式执行删除。

## HTTPS / TLS（公网域名）
已内置 Caddy 自动申请证书。请确认以下条件：
- 域名 A 记录已指向本机公网 IP
- 服务器放行 443 端口（如 80 也空闲，Caddy 可自动做 HTTP→HTTPS）

当前 compose 默认只绑定 443 端口以避免 80 冲突，证书将通过 TLS-ALPN 方式签发。

运行迁移：
```bash
docker compose exec api alembic upgrade head
```

## 手动触发采集
```bash
curl -X POST https://your-domain.example/api/ingest/run
```

查看状态：
```bash
curl https://your-domain.example/api/ingest/status/<run_id>
```

## 访问地址
- Web: https://your-domain.example
- API: https://your-domain.example/api

## 修改来源
编辑 `config/sources.yaml`，修改 RSS / HN / 搜索来源与话题标签。

## 收藏与阅读统计
- 详情页点“收藏”将永久保留该条目（不会被自动清理）。
- 自动统计浏览与阅读时长，后续可通过 `/api/analytics/items` 取回摘要与交互状态用于分析。
