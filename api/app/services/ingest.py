from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import log1p
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup
import yaml
from dateutil import parser as date_parser
import redis

from app.config import settings
from app.db.models import Source, Item, ItemTopic, IngestRun, ItemDiscussion
from app.db.session import SessionLocal
from app.services.canonicalize import canonicalize_url, content_hash
from app.services.extract import extract_article
from app.services.clean import clean_extracted_text
from app.services.summarize import summarize_article, summarize_discussion
from app.services.quality import (
    has_substantive_text,
    is_access_challenge_text,
    is_high_signal_summary,
    is_low_signal_url,
)
from app.services.translate import translate_fulltext, cache_translation
from app.services.producthunt import get_producthunt_token
from app.services.feedback import feedback_penalty_score, should_skip_candidate
from app.services import limits as limit_utils
from app.utils.http import fetch_url

CANCEL_KEY_TTL_SECONDS = 6 * 3600

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "AI效率/项目管理": [
        "productivity",
        "project management",
        "team",
        "workflow",
        "task",
        "kanban",
        "scrum",
        "okr",
        "roadmap",
        "notion",
        "协作",
        "效率",
        "项目管理",
        "知识管理",
        "任务管理",
        "看板",
        "敏捷",
    ],
    "具身智能/机器人": [
        "robot",
        "robotics",
        "embodied",
        "humanoid",
        "biped",
        "manipulation",
        "autonomous",
        "机器人",
        "具身",
        "机械臂",
        "自动驾驶",
        "无人机",
    ],
    "AI硬件/应用/实验室发布": [
        "llm",
        "model",
        "release",
        "research",
        "lab",
        "chip",
        "gpu",
        "accelerator",
        "inference",
        "foundation model",
        "fine-tuning",
        "benchmark",
        "api update",
        "sdk",
        "ai应用",
        "模型",
        "发布",
        "研究",
        "实验室",
        "硬件",
        "芯片",
        "大模型",
        "推理",
        "算力",
        "加速卡",
    ],
    "育儿/婴幼儿": [
        "baby",
        "infant",
        "toddler",
        "parenting",
        "child",
        "儿童",
        "育儿",
        "婴幼儿",
        "早教",
        "睡眠",
    ],
    "HiFi音频": [
        "hifi",
        "headphone",
        "earphone",
        "speaker",
        "dac",
        "amp",
        "audio",
        "耳机",
        "音箱",
        "解码",
        "耳放",
    ],
    "音乐推荐": [
        "music",
        "album",
        "single",
        "shoegaze",
        "emo",
        "indie",
        "音乐",
        "专辑",
        "单曲",
        "推荐",
    ],
    "宏观经济/时政": [
        "economy",
        "macro",
        "inflation",
        "rates",
        "central bank",
        "policy",
        "politics",
        "经济",
        "宏观",
        "通胀",
        "央行",
        "政策",
        "时政",
    ],
    "极客小玩意": [
        "hardware",
        "maker",
        "build",
        "diy",
        "gadget",
        "geek",
        "开源",
        "自制",
        "创客",
        "小玩意",
    ],
    "用户体验/分享": [
        "review",
        "experience",
        "opinion",
        "discussion",
        "论坛",
        "体验",
        "分享",
        "心得",
        "评测",
    ],
}

TOPIC_MIN_RATIOS: dict[str, float] = {
    "HiFi音频": 0.08,
    "音乐推荐": 0.08,
}
DEFAULT_MIN_PER_TOPIC = 1


@dataclass
class SourceConfig:
    name: str
    type: str
    config: dict[str, Any]
    topics: list[str]
    weight: float
    fetch_interval_minutes: int
    active: bool = True


@dataclass
class Candidate:
    source: SourceConfig
    url: str
    title: str
    published_at: datetime | None
    snippet: str | None
    topics: list[str]
    hn_item_id: int | None = None
    hn_points: int | None = None
    hn_comments: int | None = None


class IngestRejectedError(ValueError):
    pass


def load_sources_from_yaml(path: str = "config/sources.yaml") -> list[SourceConfig]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sources = []
    for entry in data.get("sources", []):
        sources.append(
            SourceConfig(
                name=entry["name"],
                type=entry["type"],
                config=entry,
                topics=entry.get("topics", []),
                weight=float(entry.get("weight", 1.0)),
                fetch_interval_minutes=int(entry.get("fetch_interval_minutes", 240)),
                active=bool(entry.get("active", True)),
            )
        )
    return sources


def sync_sources(session, configs: list[SourceConfig]) -> list[Source]:
    db_sources: dict[str, Source] = {s.name: s for s in session.query(Source).all()}
    results = []
    for cfg in configs:
        existing = db_sources.get(cfg.name)
        if existing:
            existing.type = cfg.type
            existing.config = cfg.config
            existing.topics = cfg.topics
            existing.weight = cfg.weight
            existing.fetch_interval_minutes = cfg.fetch_interval_minutes
            existing.active = cfg.active
            results.append(existing)
        else:
            src = Source(
                name=cfg.name,
                type=cfg.type,
                config=cfg.config,
                topics=cfg.topics,
                weight=cfg.weight,
                fetch_interval_minutes=cfg.fetch_interval_minutes,
                active=cfg.active,
            )
            session.add(src)
            results.append(src)
    session.commit()
    return results


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fetch_rss(cfg: SourceConfig) -> list[Candidate]:
    url = cfg.config.get("url")
    if not url:
        return []
    feed = feedparser.parse(url)
    candidates: list[Candidate] = []
    for entry in feed.entries:
        link = entry.get("link")
        if not link:
            continue
        title = entry.get("title", "")
        snippet = entry.get("summary") or entry.get("description")
        published = entry.get("published") or entry.get("updated")
        published_at = _parse_datetime(published)
        candidates.append(
            Candidate(
                source=cfg,
                url=link,
                title=title,
                published_at=published_at,
                snippet=snippet,
                topics=cfg.topics,
            )
        )
    return candidates


def _hn_algolia_search(query: str, tags: str = "story") -> list[dict[str, Any]]:
    url = "https://hn.algolia.com/api/v1/search"
    params = {"query": query, "tags": tags}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    return data.get("hits", [])


def _hn_top_stories(limit: int = 30) -> list[dict[str, Any]]:
    top_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(top_url)
        resp.raise_for_status()
        ids = resp.json()[:limit]
        items = []
        for item_id in ids:
            item_resp = client.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
            if item_resp.status_code != 200:
                continue
            items.append(item_resp.json())
        return items


def fetch_hn(cfg: SourceConfig) -> list[Candidate]:
    keywords = cfg.config.get("keywords", [])
    candidates: list[Candidate] = []

    for kw in keywords:
        hits = _hn_algolia_search(kw)
        for hit in hits:
            url = hit.get("url")
            if not url:
                continue
            published_at = _parse_datetime(hit.get("created_at"))
            candidates.append(
                Candidate(
                    source=cfg,
                    url=url,
                    title=hit.get("title") or "",
                    published_at=published_at,
                    snippet=hit.get("story_text"),
                    topics=cfg.topics,
                    hn_item_id=int(hit.get("objectID")) if hit.get("objectID") else None,
                    hn_points=hit.get("points"),
                    hn_comments=hit.get("num_comments"),
                )
            )

    top_items = _hn_top_stories(limit=30)
    for item in top_items:
        url = item.get("url")
        if not url:
            continue
        published_at = datetime.fromtimestamp(item.get("time"), tz=timezone.utc) if item.get("time") else None
        candidates.append(
            Candidate(
                source=cfg,
                url=url,
                title=item.get("title") or "",
                published_at=published_at,
                snippet=None,
                topics=cfg.topics,
                hn_item_id=item.get("id"),
                hn_points=item.get("score"),
                hn_comments=item.get("descendants"),
            )
        )

    return candidates


def fetch_brave(cfg: SourceConfig) -> list[Candidate]:
    if not settings.brave_search_api_key:
        return []
    query = cfg.config.get("query")
    if not query:
        return []
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"X-Subscription-Token": settings.brave_search_api_key}
    params = {"q": query, "count": 10}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
    results = data.get("web", {}).get("results", [])
    candidates: list[Candidate] = []
    for item in results:
        candidates.append(
            Candidate(
                source=cfg,
                url=item.get("url"),
                title=item.get("title") or "",
                published_at=_parse_datetime(item.get("age")),
                snippet=item.get("description"),
                topics=cfg.topics,
            )
        )
    return candidates


def fetch_newsapi(cfg: SourceConfig) -> list[Candidate]:
    if not settings.newsapi_key:
        return []
    query = cfg.config.get("query")
    if not query:
        return []
    url = "https://newsapi.org/v2/everything"
    params = {"q": query, "pageSize": 20, "sortBy": "publishedAt", "apiKey": settings.newsapi_key}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    articles = data.get("articles", [])
    candidates: list[Candidate] = []
    for item in articles:
        candidates.append(
            Candidate(
                source=cfg,
                url=item.get("url"),
                title=item.get("title") or "",
                published_at=_parse_datetime(item.get("publishedAt")),
                snippet=item.get("description"),
                topics=cfg.topics,
            )
        )
    return candidates


def fetch_producthunt(cfg: SourceConfig) -> list[Candidate]:
    token = get_producthunt_token()
    if not token:
        return []
    first = int(cfg.config.get("first", 20))
    query = """
    query($first: Int!) {
      posts(first: $first) {
        edges {
          node {
            id
            name
            tagline
            url
            website
            votesCount
            commentsCount
            featuredAt
            createdAt
          }
        }
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            "https://api.producthunt.com/v2/api/graphql",
            json={"query": query, "variables": {"first": first}},
            headers=headers,
        )
        if resp.status_code >= 400:
            return []
        data = resp.json()
    edges = data.get("data", {}).get("posts", {}).get("edges", [])
    candidates: list[Candidate] = []
    for edge in edges:
        node = edge.get("node") or {}
        url = node.get("website") or node.get("url")
        if not url:
            continue
        published_at = _parse_datetime(node.get("featuredAt") or node.get("createdAt"))
        candidates.append(
            Candidate(
                source=cfg,
                url=url,
                title=node.get("name") or "",
                published_at=published_at,
                snippet=node.get("tagline"),
                topics=cfg.topics,
            )
        )
    return candidates


def fetch_candidates(cfg: SourceConfig) -> list[Candidate]:
    if cfg.type == "rss":
        return fetch_rss(cfg)
    if cfg.type == "hn":
        return fetch_hn(cfg)
    if cfg.type == "brave":
        return fetch_brave(cfg)
    if cfg.type == "newsapi":
        return fetch_newsapi(cfg)
    if cfg.type == "producthunt":
        return fetch_producthunt(cfg)
    return []

def infer_topics(text: str, fallback: list[str]) -> list[str]:
    if not text:
        return fallback[:2] if fallback else []
    hay = text.lower()
    scored: list[tuple[str, int]] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in hay:
                score += 1
        if score:
            scored.append((topic, score))
    if not scored:
        return fallback[:2] if fallback else []
    scored.sort(key=lambda item: item[1], reverse=True)
    selected: list[str] = []
    for topic, _ in scored:
        if topic not in selected:
            selected.append(topic)
        if len(selected) >= 2:
            break
    return selected


def select_diverse_candidates(
    new_candidates: list[tuple[Candidate, float, str]],
    topics: list[str],
    max_items: int,
) -> list[tuple[Candidate, float, str]]:
    if max_items <= 0:
        return []
    if not topics:
        return new_candidates[:max_items]

    remaining = sorted(new_candidates, key=lambda x: x[1], reverse=True)
    used: set[str] = set()
    selected: list[tuple[Candidate, float, str]] = []

    buckets: dict[str, list[tuple[Candidate, float, str]]] = {t: [] for t in topics}
    for cand, score, canonical in remaining:
        for topic in cand.topics:
            if topic in buckets:
                buckets[topic].append((cand, score, canonical))

    for topic in topics:
        bucket = buckets.get(topic) or []
        if not bucket:
            continue
        bucket.sort(key=lambda x: x[1], reverse=True)
        ratio = TOPIC_MIN_RATIOS.get(topic, 0.0)
        target = DEFAULT_MIN_PER_TOPIC
        if ratio > 0:
            target = max(target, int(max_items * ratio))
        count = 0
        for cand, score, canonical in bucket:
            if canonical in used:
                continue
            selected.append((cand, score, canonical))
            used.add(canonical)
            count += 1
            if count >= target:
                break
        if len(selected) >= max_items:
            return selected

    for cand, score, canonical in remaining:
        if canonical in used:
            continue
        selected.append((cand, score, canonical))
        used.add(canonical)
        if len(selected) >= max_items:
            break

    return selected


def _score_candidate(candidate: Candidate, now: datetime) -> float:
    source_weight = candidate.source.weight
    published = candidate.published_at or now
    age_hours = max(0.0, (now - published).total_seconds() / 3600)
    recency_score = max(0.0, 1.0 - age_hours / 72.0)
    topic_score = min(1.0, len(candidate.topics) * 0.2)
    engagement = 0.0
    if candidate.hn_points is not None:
        engagement += log1p(max(candidate.hn_points, 0))
    if candidate.hn_comments is not None:
        engagement += 0.5 * log1p(max(candidate.hn_comments, 0))
    dislike_penalty = feedback_penalty_score(
        site_name=candidate.source.name,
        url=candidate.url,
        topics=candidate.topics,
    )
    return source_weight + recency_score * 2.0 + topic_score + engagement * 0.3 - dislike_penalty


FORUM_SOURCE_HINTS = ("linux.do", "v2ex", "forum")
FORUM_SOURCE_HOSTS = ("linux.do", "v2ex.com")


def _is_forum_source(cfg: SourceConfig) -> bool:
    name = (cfg.name or "").lower()
    if any(hint in name for hint in FORUM_SOURCE_HINTS):
        return True
    source_url = str(cfg.config.get("url") or "").lower()
    return any(host in source_url for host in FORUM_SOURCE_HOSTS)


def _candidate_rank_tuple(candidate: Candidate) -> tuple[datetime, int, int]:
    published = candidate.published_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
    points = candidate.hn_points or 0
    comments = candidate.hn_comments or 0
    return published, points, comments


def _limit_source_candidates(cfg: SourceConfig, fetched: list[Candidate]) -> list[Candidate]:
    if not fetched:
        return []

    limit = max(1, settings.max_candidates_per_source)
    if _is_forum_source(cfg):
        limit = min(limit, max(1, settings.max_forum_candidates_per_source))

    deduped: dict[str, Candidate] = {}
    for cand in fetched:
        if not cand.url:
            continue
        try:
            canonical = canonicalize_url(cand.url)
        except Exception:
            continue
        existing = deduped.get(canonical)
        if existing is None or _candidate_rank_tuple(cand) > _candidate_rank_tuple(existing):
            deduped[canonical] = cand

    ranked = sorted(deduped.values(), key=_candidate_rank_tuple, reverse=True)
    return ranked[:limit]


def _placeholder_image() -> str:
    return f"{settings.api_base_url}/static/placeholder.svg"


def _download_image(url: str, url_canonical: str) -> str | None:
    if not settings.download_images:
        return url
    if not url:
        return None
    try:
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix or ".jpg"
        filename = f"{content_hash(url_canonical)}{ext}"
        media_dir = Path(settings.media_dir)
        media_dir.mkdir(parents=True, exist_ok=True)
        path = media_dir / filename
        if path.exists():
            return f"{settings.api_base_url}/media/{filename}"
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return url
            path.write_bytes(resp.content)
        return f"{settings.api_base_url}/media/{filename}"
    except Exception:
        return url


def _extract_title_and_snippet(html: str, base_url: str) -> tuple[str | None, str | None]:
    if not html:
        return None, None
    soup = BeautifulSoup(html, "lxml")
    title = None
    og_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find(
        "meta", attrs={"name": "twitter:title"}
    )
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    desc = None
    og_desc = soup.find("meta", attrs={"property": "og:description"}) or soup.find(
        "meta", attrs={"name": "description"}
    )
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"].strip()
    return title, desc


def _fetch_hn_comments(item_id: int) -> list[str]:
    url = f"https://hn.algolia.com/api/v1/items/{item_id}"
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()
    comments = []
    for child in data.get("children", []):
        text = child.get("text")
        if not text:
            continue
        clean = BeautifulSoup(text, "lxml").get_text(" ", strip=True)
        if not clean:
            continue
        comments.append(clean)
        if len(comments) >= settings.hn_comments_limit:
            break
    return comments


def _redis_client() -> redis.Redis | None:
    return limit_utils.redis_client()


def _run_log_path(run_id: str) -> Path:
    base = Path(settings.log_dir) / "ingest"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{run_id}.log"


def _run_log(run_id: str | None, message: str) -> None:
    if not run_id:
        return
    try:
        path = _run_log_path(run_id)
        with open(path, "a", encoding="utf-8") as fh:
            ts = datetime.now(timezone.utc).isoformat()
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        return


def _cancel_key(run_id: str) -> str:
    return f"ingest:cancel:{run_id}"


def _should_cancel(
    session: SessionLocal, run: IngestRun, client: redis.Redis | None, check_db: bool = False
) -> bool:
    if run.status in {"cancel_requested", "canceled"}:
        return True
    if client is not None and run.id:
        try:
            if client.get(_cancel_key(run.id)):
                return True
        except Exception:
            pass
    if check_db and run.id:
        try:
            status = session.query(IngestRun.status).filter(IngestRun.id == run.id).scalar()
            if status in {"cancel_requested", "canceled"}:
                if client is not None:
                    try:
                        client.setex(_cancel_key(run.id), CANCEL_KEY_TTL_SECONDS, "1")
                    except Exception:
                        pass
                return True
        except Exception:
            return False
    return False


def _mark_canceled(session: SessionLocal, run: IngestRun) -> None:
    now = datetime.now(timezone.utc)
    run.status = "canceled"
    run.canceled_at = now
    run.finished_at = now
    session.commit()


def run_ingest(
    mode: str = "scheduled",
    run_id: str | None = None,
    source_names: list[str] | None = None,
) -> str:
    session = SessionLocal()
    client = _redis_client()
    if run_id:
        run = session.query(IngestRun).filter(IngestRun.id == run_id).first()
        if not run:
            run = IngestRun(id=run_id, mode=mode, status="running")
            session.add(run)
            session.commit()
        else:
            if _should_cancel(session, run, client, check_db=True):
                _mark_canceled(session, run)
                _run_log(run.id, "canceled before start")
                return run.id
            run.mode = mode
            run.status = "running"
            session.commit()
    else:
        run = IngestRun(mode=mode, status="running")
        session.add(run)
        session.commit()
    _run_log(run.id, f"start mode={mode} source_filter={source_names or 'all'}")

    try:
        if _should_cancel(session, run, client, check_db=True):
            _mark_canceled(session, run)
            _run_log(run.id, "canceled before loading sources")
            return run.id

        configs = load_sources_from_yaml()
        if source_names:
            allow = {name.strip().lower() for name in source_names if name}
            configs = [cfg for cfg in configs if cfg.name.lower() in allow]
        sources = sync_sources(session, configs)
        source_map = {s.name: s for s in sources}
        _run_log(run.id, f"sources loaded: {len(configs)}")

        candidates: list[Candidate] = []
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max(1, settings.max_item_age_days))
        run.started_at = now
        session.commit()
        for cfg in configs:
            if _should_cancel(session, run, client):
                _mark_canceled(session, run)
                _run_log(run.id, "canceled during source fetch")
                return run.id
            if not cfg.active:
                _run_log(run.id, f"skip source (inactive): {cfg.name}")
                continue
            db_source = source_map.get(cfg.name)
            if mode == "scheduled" and db_source and db_source.last_fetch_at:
                if db_source.last_fetch_at + timedelta(minutes=cfg.fetch_interval_minutes) > now:
                    _run_log(run.id, f"skip source (interval): {cfg.name}")
                    continue
            try:
                _run_log(run.id, f"fetch source: {cfg.name}")
                fetched_raw = fetch_candidates(cfg)
                fetched = _limit_source_candidates(cfg, fetched_raw)
                candidates.extend(fetched)
                if len(fetched) != len(fetched_raw):
                    _run_log(
                        run.id,
                        f"fetched {len(fetched_raw)} candidates from {cfg.name} (kept {len(fetched)})",
                    )
                else:
                    _run_log(run.id, f"fetched {len(fetched)} candidates from {cfg.name}")
            except Exception:
                _run_log(run.id, f"fetch error {cfg.name}")
                continue
            if db_source:
                db_source.last_fetch_at = now

        session.commit()

        run.total_candidates = len(candidates)
        session.commit()
        _run_log(run.id, f"total candidates: {len(candidates)}")

        topic_list: list[str] = []
        for cfg in configs:
            for topic in cfg.topics:
                if topic not in topic_list:
                    topic_list.append(topic)

        seen_urls: set[str] = set()
        new_candidates: list[tuple[Candidate, float, str]] = []

        for idx, cand in enumerate(candidates):
            if _should_cancel(session, run, client, check_db=idx % 20 == 0):
                _mark_canceled(session, run)
                _run_log(run.id, "canceled during candidate filtering")
                return run.id
            if not cand.url:
                continue
            if cand.published_at and cand.published_at < cutoff:
                continue
            cand.topics = infer_topics(
                " ".join([cand.title or "", cand.snippet or "", cand.source.name or ""]),
                cand.topics,
            )
            canonical = canonicalize_url(cand.url)
            if settings.strict_signal_filter and is_low_signal_url(
                canonical,
                filter_forum_sources=settings.filter_forum_sources,
            ):
                continue
            if canonical in seen_urls:
                continue
            if session.query(Item.id).filter(Item.url_canonical == canonical).first():
                continue
            if settings.strict_signal_filter and should_skip_candidate(
                site_name=cand.source.name,
                url=canonical,
                topics=cand.topics,
            ):
                _run_log(run.id, f"skip dislike-signal {canonical}")
                continue
            seen_urls.add(canonical)
            score = _score_candidate(cand, now)
            new_candidates.append((cand, score, canonical))

        max_items = settings.max_items_per_run
        if mode == "scheduled" and settings.scheduled_max_items > 0:
            max_items = min(max_items, settings.scheduled_max_items)
        if mode == "manual":
            if source_names:
                max_items = min(max_items, settings.manual_source_max_items)
            else:
                max_items = min(max_items, settings.manual_max_items)
        selected = select_diverse_candidates(
            new_candidates,
            topic_list,
            max_items,
        )
        _run_log(run.id, f"selected {len(selected)} candidates")

        inserted = 0
        inserted_by_source: dict[int, int] = {}
        for idx, (cand, score, canonical) in enumerate(selected):
            if _should_cancel(session, run, client, check_db=idx % 10 == 0):
                _mark_canceled(session, run)
                _run_log(run.id, "canceled during insertion")
                return run.id
            try:
                extract = extract_article(canonical)
                text = (extract.text or "").strip()
                if settings.strict_signal_filter and is_access_challenge_text(text):
                    _run_log(run.id, f"skip blocked content {canonical}")
                    continue

                cleaned_text = clean_extracted_text(
                    text,
                    title=cand.title,
                    url=canonical,
                    site_name=extract.site_name,
                )
                primary_text = (cleaned_text or text or "").strip()
                if settings.strict_signal_filter and is_access_challenge_text(primary_text):
                    _run_log(run.id, f"skip blocked cleaned content {canonical}")
                    continue

                snippet = cand.snippet or ""
                if snippet and "<" in snippet:
                    snippet = BeautifulSoup(snippet, "lxml").get_text(" ", strip=True)
                snippet = snippet.strip()

                has_fulltext = False
                if settings.strict_signal_filter:
                    has_fulltext = has_substantive_text(
                        primary_text,
                        min_chars=settings.min_summary_input_chars,
                        min_paragraphs=settings.min_summary_input_paragraphs,
                    )
                    if has_fulltext:
                        summary_input = primary_text
                    else:
                        has_snippet = has_substantive_text(
                            snippet,
                            min_chars=max(180, settings.min_summary_input_chars // 2),
                            min_paragraphs=1,
                        )
                        if not has_snippet:
                            _run_log(run.id, f"skip low-content {canonical}")
                            continue
                        summary_input = snippet
                else:
                    summary_input = primary_text or snippet or cand.title

                if settings.strict_signal_filter and len(summary_input) < max(
                    80, settings.min_summary_input_chars // 3
                ):
                    _run_log(run.id, f"skip short summary input {canonical}")
                    continue

                topic_text = " ".join(
                    part for part in [summary_input, snippet, cand.title, cand.source.name] if part
                )
                final_topics = infer_topics(topic_text, cand.topics)

                try:
                    summary = summarize_article(summary_input, cand.title, final_topics)
                except Exception as exc:
                    _run_log(run.id, f"summary failed for {canonical}: {exc.__class__.__name__}")
                    continue

                if settings.strict_signal_filter and not is_high_signal_summary(
                    summary,
                    min_summary_chars=settings.min_summary_chars,
                    min_bullets=settings.min_summary_bullets,
                    min_takeaways=settings.min_practical_takeaways,
                ):
                    _run_log(run.id, f"skip low-signal summary {canonical}")
                    continue

                summary_json = summary.model_dump()
                if any("育儿" in t or "婴幼儿" in t for t in final_topics):
                    if not summary_json.get("disclaimer_zh"):
                        summary_json["disclaimer_zh"] = "本摘要仅作信息整理，不构成医疗建议。如需健康决策，请咨询专业人士。"

                item_hash = content_hash((summary_input or cand.title or "")[:4000])
                if session.query(Item.id).filter(Item.content_hash == item_hash).first():
                    continue

                image_url = extract.image_url or _placeholder_image()
                image_url = _download_image(image_url, canonical)

                site_name = extract.site_name or urlparse(canonical).netloc

                source_id = source_map[cand.source.name].id if cand.source.name in source_map else None
                item = Item(
                    url=cand.url,
                    url_canonical=canonical,
                    content_hash=item_hash,
                    title=cand.title,
                    title_zh=summary.title_zh,
                    summary_zh=summary.summary_zh,
                    summary_json=summary_json,
                    excerpt=(extract.excerpt or (snippet[: settings.excerpt_max_chars] if snippet else None) or summary.summary_zh[: settings.excerpt_max_chars]),
                    translation_excerpt=None,
                    translation_full_zh=None,
                    image_url=image_url,
                    site_name=site_name,
                    published_at=cand.published_at,
                    fetched_at=now,
                    source_id=source_id,
                    hn_item_id=cand.hn_item_id,
                    hn_points=cand.hn_points,
                    hn_comments=cand.hn_comments,
                    score=score,
                    world="real",
                )
                session.add(item)
                session.flush()

                translation_full = None
                translation_source = (primary_text if has_fulltext else snippet) or primary_text or snippet
                if settings.strict_signal_filter and translation_source:
                    if is_access_challenge_text(translation_source):
                        translation_source = ""
                    elif not has_substantive_text(
                        translation_source,
                        min_chars=max(180, settings.min_summary_input_chars // 2),
                        min_paragraphs=1,
                    ):
                        translation_source = ""
                if translation_source:
                    try:
                        translation_full = translate_fulltext(translation_source)
                    except Exception as exc:
                        _run_log(run.id, f"translation failed for {canonical}: {exc.__class__.__name__}")
                if translation_full:
                    item.translation_full_zh = translation_full
                    item.translation_excerpt = translation_full[: settings.excerpt_max_chars]
                    cache_translation(item.id, translation_full)

                for topic in final_topics:
                    session.add(ItemTopic(item_id=item.id, topic=topic))

                if cand.hn_item_id:
                    comments = _fetch_hn_comments(cand.hn_item_id)
                    if comments:
                        try:
                            discussion = summarize_discussion(comments)
                            session.add(
                                ItemDiscussion(
                                    item_id=item.id,
                                    source="hn",
                                    thread_id=str(cand.hn_item_id),
                                    summary_zh=f"共识：{discussion.consensus_zh}\n分歧：{discussion.disagreements_zh or ''}".strip(),
                                    raw_json=discussion.model_dump(),
                                )
                            )
                        except Exception as exc:
                            _run_log(run.id, f"discussion summarize failed {canonical}: {exc.__class__.__name__}")

                inserted += 1
                if source_id is not None:
                    inserted_by_source[source_id] = inserted_by_source.get(source_id, 0) + 1
                session.commit()
                _run_log(run.id, f"inserted item {item.id} from {site_name}")
            except Exception as exc:
                session.rollback()
                _run_log(run.id, f"insert failed for {canonical}: {exc.__class__.__name__}: {exc}")
                continue

        run.new_items = inserted
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        _run_log(run.id, f"completed new_items={inserted}")
        if mode == "manual":
            client = _redis_client()
        return run.id
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        _run_log(run.id, f"failed error={exc}")
        raise
    finally:
        session.close()


def ingest_single_url(url: str) -> Item:
    session = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        canonical = canonicalize_url(url)
        if settings.strict_signal_filter and is_low_signal_url(
            canonical,
            filter_forum_sources=settings.filter_forum_sources,
        ):
            raise IngestRejectedError("low_signal_url")
        existing = session.query(Item).filter(Item.url_canonical == canonical).first()
        if existing:
            return existing

        extract = extract_article(canonical)
        text = (extract.text or "").strip()
        if settings.strict_signal_filter and is_access_challenge_text(text):
            raise IngestRejectedError("blocked_content")
        cleaned_text = clean_extracted_text(
            text,
            title=None,
            url=canonical,
            site_name=extract.site_name,
        )
        primary_text = (cleaned_text or text or "").strip()
        if settings.strict_signal_filter and is_access_challenge_text(primary_text):
            raise IngestRejectedError("blocked_cleaned_content")
        title = None
        snippet = None

        if not text or not extract.site_name or not extract.image_url:
            resp = fetch_url(canonical)
            if resp is not None:
                html = resp.text
                base_url = str(resp.url)
                title, snippet = _extract_title_and_snippet(html, base_url)
                if not extract.site_name:
                    extract.site_name = urlparse(base_url).netloc
        if not extract.site_name:
            extract.site_name = urlparse(canonical).netloc

        if snippet and "<" in snippet:
            snippet = BeautifulSoup(snippet, "lxml").get_text(" ", strip=True)
        snippet = (snippet or "").strip()

        has_fulltext = False
        if settings.strict_signal_filter:
            has_fulltext = has_substantive_text(
                primary_text,
                min_chars=settings.min_summary_input_chars,
                min_paragraphs=settings.min_summary_input_paragraphs,
            )
            if has_fulltext:
                summary_input = primary_text
            else:
                has_snippet = has_substantive_text(
                    snippet,
                    min_chars=max(180, settings.min_summary_input_chars // 2),
                    min_paragraphs=1,
                )
                if not has_snippet:
                    raise IngestRejectedError("low_content")
                summary_input = snippet
        else:
            summary_input = primary_text or snippet or (title or "").strip() or canonical

        if settings.strict_signal_filter and len(summary_input) < max(
            80, settings.min_summary_input_chars // 3
        ):
            raise IngestRejectedError("short_summary_input")

        topic_text = " ".join([title or "", snippet or "", summary_input or "", extract.site_name or ""])
        final_topics = infer_topics(topic_text, ["用户体验/分享"])

        summary = summarize_article(summary_input, title, final_topics)
        if settings.strict_signal_filter and not is_high_signal_summary(
            summary,
            min_summary_chars=settings.min_summary_chars,
            min_bullets=settings.min_summary_bullets,
            min_takeaways=settings.min_practical_takeaways,
        ):
            raise IngestRejectedError("low_signal_summary")

        summary_json = summary.model_dump()
        if any("育儿" in t or "婴幼儿" in t for t in final_topics):
            if not summary_json.get("disclaimer_zh"):
                summary_json["disclaimer_zh"] = "本摘要仅作信息整理，不构成医疗建议。如需健康决策，请咨询专业人士。"

        item_hash = content_hash((summary_input or title or "")[:4000])
        existing_hash = session.query(Item).filter(Item.content_hash == item_hash).first()
        if existing_hash:
            return existing_hash

        image_url = extract.image_url or _placeholder_image()
        image_url = _download_image(image_url, canonical)

        item = Item(
            url=canonical,
            url_canonical=canonical,
            content_hash=item_hash,
            title=title or summary.title_zh or canonical,
            title_zh=summary.title_zh,
            summary_zh=summary.summary_zh,
            summary_json=summary_json,
            excerpt=(extract.excerpt or (snippet[: settings.excerpt_max_chars] if snippet else None) or summary.summary_zh[: settings.excerpt_max_chars]),
            translation_excerpt=None,
            translation_full_zh=None,
            image_url=image_url,
            site_name=extract.site_name,
            published_at=None,
            fetched_at=now,
            score=0.0,
            world="real",
        )
        session.add(item)
        session.flush()

        translation_full = None
        translation_source = (primary_text if has_fulltext else snippet) or primary_text or snippet
        if settings.strict_signal_filter and translation_source:
            if is_access_challenge_text(translation_source):
                translation_source = ""
            elif not has_substantive_text(
                translation_source,
                min_chars=max(180, settings.min_summary_input_chars // 2),
                min_paragraphs=1,
            ):
                translation_source = ""
        if translation_source:
            try:
                translation_full = translate_fulltext(translation_source)
            except Exception:
                translation_full = None
        if translation_full:
            item.translation_full_zh = translation_full
            item.translation_excerpt = translation_full[: settings.excerpt_max_chars]
            cache_translation(item.id, translation_full)

        for topic in final_topics:
            session.add(ItemTopic(item_id=item.id, topic=topic))

        session.commit()
        session.refresh(item)
        return item
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
