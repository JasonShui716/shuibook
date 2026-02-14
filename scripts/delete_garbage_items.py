from __future__ import annotations

import argparse
import json
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import redis
from openai import OpenAI
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Item
from app.db.session import SessionLocal

BLOCKED_MARKERS = (
    "just a moment",
    "attention required",
    "cf-browser-verification",
    "cf-chl",
    "challenge-platform",
    "cloudflare",
    "verify you are human",
    "access denied",
    "captcha",
    "ddos protection",
    "检测到异常流量",
    "请完成验证",
    "安全验证",
    "人机验证",
    "访问受限",
)

LOW_SIGNAL_MARKERS = (
    "信息量不足，建议跳过",
    "原文信息不足",
    "无法提炼出关键事实",
    "建议直接阅读原文",
)

SUSPECT_SITES = (
    "linux.do",
    "v2ex.com",
    "www.v2ex.com",
)

KEEP_REASON_MARKERS = (
    "支持精读",
    "信息完整",
    "包含明确事实",
    "包含关键事实",
    "可读",
    "有价值",
    "支持后续阅读",
)


@dataclass(slots=True)
class ItemSnapshot:
    id: int
    title_zh: str | None
    summary_zh: str | None
    translation_full_zh: str | None
    translation_excerpt: str | None
    excerpt: str | None
    source: str | None
    url: str | None
    is_favorite: bool


@dataclass(slots=True)
class JudgeResult:
    item_id: int
    action: str
    reason: str
    confidence: float


_thread_local = threading.local()


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str | None, markers: tuple[str, ...]) -> bool:
    lower = _normalize(text).lower()
    if not lower:
        return False
    return any(marker in lower for marker in markers)


def _heuristic_garbage(snapshot: ItemSnapshot) -> str | None:
    merged = "\n".join(
        filter(
            None,
            [
                snapshot.summary_zh,
                snapshot.translation_full_zh,
                snapshot.translation_excerpt,
                snapshot.excerpt,
            ],
        )
    )
    if _contains_any(merged, BLOCKED_MARKERS):
        return "blocked_or_verification_page"

    summary = _normalize(snapshot.summary_zh)
    translation = _normalize(snapshot.translation_full_zh)

    if summary and any(marker in summary for marker in LOW_SIGNAL_MARKERS):
        return "low_signal_summary"

    if translation:
        # 机器翻译文本极短通常不可读。
        if len(translation) < 120:
            return "translation_too_short"
        if _contains_any(translation, BLOCKED_MARKERS):
            return "translation_contains_blocked_marker"

    src = (snapshot.source or "").lower()
    if src in SUSPECT_SITES and len(summary) < 140 and len(translation) < 180:
        return "forum_low_info"

    return None


def _json_loads_safe(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


def _client() -> OpenAI:
    client = getattr(_thread_local, "openai_client", None)
    if client is not None:
        return client
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    client = OpenAI(api_key=settings.openai_api_key)
    _thread_local.openai_client = client
    return client


def _looks_keep_reason(reason: str) -> bool:
    normalized = _normalize(reason)
    if not normalized:
        return False
    return any(marker in normalized for marker in KEEP_REASON_MARKERS)


def _llm_judge(snapshot: ItemSnapshot, model: str) -> tuple[str, str, str, float]:
    prompt = {
        "task": "判断信息流条目是否属于应删除垃圾内容",
        "delete_if": [
            "被安全验证/反爬页面挡住，正文不可读",
            "翻译严重失真或几乎无信息量",
            "内容主要是站点模板、广告、噪音，无法支持精读",
            "摘要与正文都缺乏关键事实（时间、主体、事件、影响）",
        ],
        "keep_if": [
            "虽然简短但包含明确事实且可读",
            "可支持后续精读或有明确信息价值",
        ],
        "output": {
            "verdict": "delete|keep",
            "category": "blocked_page|translation_noise|template_noise|low_fact_density|useful_content",
            "reason": "short string",
            "confidence": "0-1 float",
        },
        "item": {
            "title_zh": snapshot.title_zh,
            "summary_zh": snapshot.summary_zh,
            "translation_full_zh": (snapshot.translation_full_zh or "")[:1800],
            "translation_excerpt": (snapshot.translation_excerpt or "")[:800],
            "excerpt": (snapshot.excerpt or "")[:800],
            "source": snapshot.source,
            "url": snapshot.url,
        },
    }

    last_exc: Exception | None = None
    resp = None
    for attempt in range(4):
        try:
            resp = _client().chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "你是严格内容质检器，只输出 JSON。"},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            break
        except Exception as exc:
            last_exc = exc
            name = exc.__class__.__name__
            msg = str(exc).lower()
            transient = name in {"RateLimitError", "APIConnectionError", "APITimeoutError"} or "rate limit" in msg
            if not transient or attempt >= 3:
                raise
            time.sleep(1.2 * (2**attempt))
    if resp is None:
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("empty llm response")
    raw = resp.choices[0].message.content or "{}"
    data = _json_loads_safe(raw)
    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in {"delete", "keep"}:
        # 兼容旧返回格式，避免解析失败导致误删。
        verdict = "delete" if bool(data.get("is_garbage", False)) else "keep"
    category = str(data.get("category") or "unknown").strip().lower()[:48]
    reason = str(data.get("reason") or "llm_decision")[:160]
    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # 防误删：当模型输出删除，但理由语义明显属于“应保留”时，强制改为保留。
    if verdict == "delete" and _looks_keep_reason(reason):
        verdict = "keep"
        category = "reason_conflict_keep"
        confidence = min(confidence, 0.55)
    return verdict, category, reason, confidence


def _redis_client() -> redis.Redis | None:
    try:
        return redis.Redis.from_url(settings.redis_url)
    except Exception:
        return None


def _delete_item(item_id: int, reason: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    session: Session = SessionLocal()
    try:
        item = session.query(Item).filter(Item.id == item_id).first()
        if not item:
            return False
        session.delete(item)
        session.commit()
    except Exception:
        session.rollback()
        return False
    finally:
        session.close()

    client = _redis_client()
    if client is not None:
        try:
            client.delete(f"translation:{item_id}")
        except Exception:
            pass
    return True


def _fetch_snapshots(
    limit: int | None,
    include_favorites: bool,
    all_items: bool,
    item_ids: list[int] | None,
) -> list[ItemSnapshot]:
    session: Session = SessionLocal()
    try:
        query = session.query(Item).filter(Item.world == "real", Item.is_disliked.is_(False))
        if not include_favorites:
            query = query.filter(Item.is_favorite.is_(False))
        if item_ids:
            query = query.filter(Item.id.in_(sorted(set(item_ids))))

        if not all_items:
            query = query.filter(
                or_(
                    Item.translation_full_zh.isnot(None),
                    Item.translation_excerpt.isnot(None),
                    Item.summary_zh.ilike("%信息量不足%"),
                    Item.summary_zh.ilike("%建议直接阅读原文%"),
                    Item.site_name.in_(SUSPECT_SITES),
                    Item.excerpt.ilike("%验证%"),
                )
            )

        query = query.order_by(Item.id.asc())
        if limit is not None and limit > 0:
            query = query.limit(limit)

        rows = query.all()
        return [
            ItemSnapshot(
                id=row.id,
                title_zh=row.title_zh,
                summary_zh=row.summary_zh,
                translation_full_zh=row.translation_full_zh,
                translation_excerpt=row.translation_excerpt,
                excerpt=row.excerpt,
                source=row.site_name,
                url=row.url_canonical or row.url,
                is_favorite=bool(row.is_favorite),
            )
            for row in rows
        ]
    finally:
        session.close()


def _process_one(
    snapshot: ItemSnapshot,
    model: str,
    min_confidence: float,
    dry_run: bool,
    use_llm: bool,
) -> JudgeResult:
    heuristic_reason = _heuristic_garbage(snapshot)
    if heuristic_reason:
        deleted = _delete_item(snapshot.id, heuristic_reason, dry_run=dry_run)
        return JudgeResult(
            item_id=snapshot.id,
            action="deleted" if deleted else "delete_failed",
            reason=f"heuristic:{heuristic_reason}",
            confidence=1.0,
        )

    if not use_llm:
        return JudgeResult(item_id=snapshot.id, action="kept", reason="no_heuristic_match", confidence=0.0)

    try:
        verdict, category, reason, confidence = _llm_judge(snapshot, model=model)
    except Exception as exc:
        return JudgeResult(item_id=snapshot.id, action="error", reason=f"llm_error:{exc.__class__.__name__}", confidence=0.0)

    if verdict != "delete":
        return JudgeResult(item_id=snapshot.id, action="kept", reason=f"llm_keep:{category}:{reason}", confidence=confidence)

    if confidence < min_confidence:
        return JudgeResult(
            item_id=snapshot.id,
            action="kept",
            reason=f"llm_low_conf:{category}:{reason}",
            confidence=confidence,
        )

    deleted = _delete_item(snapshot.id, reason, dry_run=dry_run)
    return JudgeResult(
        item_id=snapshot.id,
        action="deleted" if deleted else "delete_failed",
        reason=f"llm:{category}:{reason}",
        confidence=confidence,
    )


def run(
    workers: int,
    model: str,
    min_confidence: float,
    limit: int | None,
    dry_run: bool,
    include_favorites: bool,
    all_items: bool,
    no_llm: bool,
    item_ids: list[int] | None,
) -> None:
    snapshots = _fetch_snapshots(
        limit=limit,
        include_favorites=include_favorites,
        all_items=all_items,
        item_ids=item_ids,
    )
    total = len(snapshots)
    if total == 0:
        print("no candidates")
        return

    print(
        f"start garbage cleanup: candidates={total}, workers={workers}, model={model}, "
        f"dry_run={dry_run}, all_items={all_items}, use_llm={not no_llm}"
    )

    counters = Counter()
    reason_counter = Counter()

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                _process_one,
                snap,
                model,
                min_confidence,
                dry_run,
                not no_llm,
            ): snap.id
            for snap in snapshots
        }
        for idx, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            counters[result.action] += 1
            reason_counter[result.reason] += 1
            if result.action in {"deleted", "delete_failed", "error"}:
                print(
                    f"[{idx}/{total}] item={result.item_id} action={result.action} "
                    f"reason={result.reason} conf={result.confidence:.2f}"
                )

    print("summary:")
    for key in sorted(counters.keys()):
        print(f"  {key}: {counters[key]}")

    print("top reasons:")
    for reason, count in reason_counter.most_common(20):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="并行垃圾内容清理器")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--model", type=str, default="gpt-4.1-nano")
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-favorites", action="store_true")
    parser.add_argument("--all-items", action="store_true", help="默认仅清理疑似垃圾，开启后扫描全部 real items")
    parser.add_argument("--no-llm", action="store_true", help="仅启发式清理")
    parser.add_argument("--ids", nargs="+", type=int, default=None, help="仅清理指定 item id 列表")
    args = parser.parse_args()

    run(
        workers=args.workers,
        model=args.model,
        min_confidence=max(0.0, min(1.0, args.min_confidence)),
        limit=args.limit,
        dry_run=args.dry_run,
        include_favorites=args.include_favorites,
        all_items=args.all_items,
        no_llm=args.no_llm,
        item_ids=args.ids,
    )
