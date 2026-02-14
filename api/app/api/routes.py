from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any
import random

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi import Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_
import redis
import secrets
from pathlib import Path
import yaml
import pyotp

from app.api.deps import get_db
from app.db.models import Item, ItemTopic, IngestRun, Source
from app.workers.tasks import run_ingest_task
from app.services.ingest import IngestRejectedError, ingest_single_url
from app.workers.celery_app import celery_app
from app.services.translate import get_cached_translation
from app.services.feedback import (
    batch_feedback_penalties,
    record_dislike_feedback,
    revert_dislike_feedback,
)
from app.config import settings
from app.services import limits as limit_utils


router = APIRouter()
LONG_READ_SECONDS = 30
CANCEL_KEY_TTL_SECONDS = 6 * 3600
CANCEL_STALE_MINUTES = 15


def _serialize_item(item: Item) -> dict[str, Any]:
    topics = [t.topic for t in item.topics]
    return {
        "id": item.id,
        "title_zh": item.title_zh,
        "summary_zh": item.summary_zh,
        "excerpt": (item.summary_zh or "")[:120],
        "image_url": item.image_url,
        "topics": topics,
        "source": item.site_name,
        "published_at": item.published_at,
        "fetched_at": item.fetched_at,
        "is_favorite": item.is_favorite,
        "is_disliked": item.is_disliked,
        "world": item.world,
        "ai_topic": item.ai_topic,
    }


def _serialize_detail(item: Item) -> dict[str, Any]:
    topics = [t.topic for t in item.topics]
    discussion = None
    if item.discussions:
        discussion = item.discussions[0].summary_zh
    summary_json = item.summary_json or {}
    translation_full = item.translation_full_zh or get_cached_translation(item.id)
    read_original = item.url
    full_content = summary_json.get("full_content_zh") or summary_json.get("content_zh")
    return {
        "id": item.id,
        "title_zh": item.title_zh,
        "summary_zh": item.summary_zh,
        "summary_json": summary_json,
        "what_happened_zh": summary_json.get("what_happened_zh") or item.summary_zh,
        "why_it_matters_zh": summary_json.get("why_it_matters_zh") or "".join(summary_json.get("practical_takeaways", [])[:2]),
        "practical_takeaways": summary_json.get("practical_takeaways", []),
        "controversy_points": summary_json.get("controversy_points", []),
        "disclaimer_zh": summary_json.get("disclaimer_zh"),
        "full_content_zh": full_content,
        "translation_zh": translation_full or item.translation_excerpt,
        "translation_is_full": bool(translation_full),
        "image_url": item.image_url,
        "topics": topics,
        "source": item.site_name,
        "published_at": item.published_at,
        "fetched_at": item.fetched_at,
        "read_original": read_original,
        "people_takes": discussion,
        "is_favorite": item.is_favorite,
        "favorited_at": item.favorited_at,
        "is_disliked": item.is_disliked,
        "disliked_at": item.disliked_at,
        "view_count": item.view_count,
        "last_viewed_at": item.last_viewed_at,
        "total_read_seconds": item.total_read_seconds,
        "long_read_count": item.long_read_count,
        "world": item.world,
        "ai_topic": item.ai_topic,
    }


def _parse_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        ts_str, id_str = cursor.split("|", 1)
        ts = datetime.fromisoformat(ts_str)
        return ts, int(id_str)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


def _normalize_feed_order(order: str | None, randomize: bool) -> str:
    value = (order or "").strip().lower()
    if not value:
        return "random" if randomize else "time"
    if value in {"random", "shuffle"}:
        return "random"
    if value in {"time", "latest", "newest", "chronological"}:
        return "time"
    raise HTTPException(status_code=400, detail="Invalid order")


def _apply_dislike_feedback(items: list[Item], min_keep: int) -> list[Item]:
    if not items:
        return items
    records: list[tuple[str | None, str | None, list[str]]] = []
    for item in items:
        records.append(
            (
                item.site_name,
                item.url_canonical or item.url,
                [topic.topic for topic in item.topics],
            )
        )
    penalties = batch_feedback_penalties(records)
    scored = list(zip(items, penalties))
    strong_filtered = [item for item, penalty in scored if penalty < 2.3]
    if len(strong_filtered) >= min_keep:
        return strong_filtered
    relaxed_filtered = [item for item, penalty in scored if penalty < 3.0]
    if len(relaxed_filtered) >= min_keep:
        return relaxed_filtered
    return items


def _parse_run_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        ts_str, run_id = cursor.split("|", 1)
        ts = datetime.fromisoformat(ts_str)
        return ts, run_id
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid run cursor") from exc


def _redis_client():
    return limit_utils.redis_client()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _otp_ip_keys(ip: str) -> tuple[str, str]:
    return f"admin:otp:ip:{ip}", f"admin:otp:ip:{ip}:lock"


def _otp_global_keys() -> tuple[str, str]:
    return "admin:otp:global", "admin:otp:global:lock"


def _get_ttl(client: redis.Redis, key: str) -> int | None:
    try:
        ttl = client.ttl(key)
        if ttl and ttl > 0:
            return int(ttl)
    except Exception:
        return None
    return None


def _check_admin_otp_limit(client: redis.Redis | None, ip: str) -> tuple[bool, int | None]:
    if client is None:
        return True, None
    _, ip_lock_key = _otp_ip_keys(ip)
    _, global_lock_key = _otp_global_keys()
    if client.get(ip_lock_key):
        return False, _get_ttl(client, ip_lock_key)
    if client.get(global_lock_key):
        return False, _get_ttl(client, global_lock_key)
    return True, None


def _record_admin_otp_failure(client: redis.Redis | None, ip: str) -> None:
    if client is None:
        return
    ip_count_key, ip_lock_key = _otp_ip_keys(ip)
    global_count_key, global_lock_key = _otp_global_keys()
    try:
        ip_count = client.incr(ip_count_key, 1)
        client.expire(ip_count_key, settings.admin_otp_ip_window_seconds)
        if ip_count >= settings.admin_otp_ip_max_attempts:
            client.setex(ip_lock_key, settings.admin_otp_ip_lock_seconds, "1")
        global_count = client.incr(global_count_key, 1)
        client.expire(global_count_key, settings.admin_otp_global_window_seconds)
        if global_count >= settings.admin_otp_global_max_attempts:
            client.setex(global_lock_key, settings.admin_otp_global_lock_seconds, "1")
    except Exception:
        return


def _clear_admin_otp_failures(client: redis.Redis | None, ip: str) -> None:
    if client is None:
        return
    ip_count_key, ip_lock_key = _otp_ip_keys(ip)
    try:
        client.delete(ip_count_key, ip_lock_key)
    except Exception:
        return


def _cancel_key(run_id: str) -> str:
    return f"ingest:cancel:{run_id}"


def _reconcile_cancel_status(run: IngestRun, db: Session) -> None:
    if run.status != "cancel_requested":
        return
    now = datetime.now(timezone.utc)
    if run.celery_task_id:
        try:
            result = celery_app.AsyncResult(run.celery_task_id)
            state = result.state
        except Exception:
            state = None
        if state == "REVOKED":
            run.status = "canceled"
            run.canceled_at = now
            run.finished_at = now
            db.commit()
            return
        if state == "FAILURE":
            run.status = "failed"
            run.finished_at = now
            if not run.error:
                run.error = "celery_task_failed_after_cancel"
            db.commit()
            return
        if state == "SUCCESS":
            run.status = "completed"
            run.finished_at = run.finished_at or now
            db.commit()
            return
    if run.cancel_requested_at and now - run.cancel_requested_at > timedelta(minutes=CANCEL_STALE_MINUTES):
        run.status = "canceled"
        run.canceled_at = now
        run.finished_at = now
        if not run.error:
            run.error = "cancel_timeout"
        db.commit()


def _admin_token_key(token: str) -> str:
    return f"admin:token:{token}"


def _store_admin_token(token: str) -> None:
    client = _redis_client()
    if client is None:
        return
    ttl = max(1, settings.admin_session_ttl_hours) * 3600
    client.setex(_admin_token_key(token), ttl, "1")


def _verify_admin_token(token: str | None) -> bool:
    if not token:
        return False
    client = _redis_client()
    if client is None:
        return False
    return bool(client.get(_admin_token_key(token)))


def _require_admin(token: str | None = Header(None, alias="X-Admin-Token")) -> None:
    if not settings.admin_totp_secret:
        raise HTTPException(status_code=503, detail="Admin OTP not configured")
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _ingest_limits(_: Session) -> dict[str, Any]:
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)
    now_utc = datetime.now(timezone.utc)
    count_key, last_key, _ = limit_utils.limit_keys(now_local)
    client = _redis_client()
    daily_used = 0
    last_ts = None
    if client is not None:
        try:
            raw_count = client.get(count_key)
            daily_used = int(raw_count) if raw_count else 0
            raw_last = client.get(last_key)
            if raw_last:
                last_ts = float(raw_last)
        except Exception:
            daily_used = 0
            last_ts = None

    next_allowed_at = None
    if last_ts:
        min_next = datetime.fromtimestamp(last_ts, tz=timezone.utc) + timedelta(
            seconds=limit_utils.MANUAL_MIN_INTERVAL_SECONDS
        )
        if min_next > now_utc:
            next_allowed_at = min_next

    end_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_utc = end_local.astimezone(timezone.utc)
    if daily_used >= limit_utils.MANUAL_DAILY_LIMIT and end_utc > now_utc:
        next_allowed_at = max(next_allowed_at or end_utc, end_utc)

    allowed = daily_used < limit_utils.MANUAL_DAILY_LIMIT and (
        next_allowed_at is None or now_utc >= next_allowed_at
    )
    daily_remaining = max(0, limit_utils.MANUAL_DAILY_LIMIT - daily_used)

    return {
        "allowed": allowed,
        "daily_limit": limit_utils.MANUAL_DAILY_LIMIT,
        "daily_used": daily_used,
        "daily_remaining": daily_remaining,
        "min_interval_seconds": limit_utils.MANUAL_MIN_INTERVAL_SECONDS,
        "next_allowed_at": next_allowed_at.isoformat() if next_allowed_at else None,
        "server_time": now_utc.isoformat(),
        "timezone": settings.timezone,
    }


def _reserve_manual_slot() -> None:
    client = _redis_client()
    limit_utils.reserve_manual_interval(client)
    # 计数按“触发次数”而非入库条数
    limit_utils.increment_manual_count(client, 1)


def _check_source_limit(source_id: int) -> dict[str, Any]:
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)
    now_utc = datetime.now(timezone.utc)
    count_key, last_key, _ = limit_utils.source_limit_keys(now_local, source_id)
    client = _redis_client()
    daily_used = 0
    last_ts = None
    if client is not None:
        try:
            raw_count = client.get(count_key)
            daily_used = int(raw_count) if raw_count else 0
            raw_last = client.get(last_key)
            if raw_last:
                last_ts = float(raw_last)
        except Exception:
            daily_used = 0
            last_ts = None

    next_allowed_at = None
    if last_ts:
        min_next = datetime.fromtimestamp(last_ts, tz=timezone.utc) + timedelta(
            seconds=limit_utils.MANUAL_MIN_INTERVAL_SECONDS
        )
        if min_next > now_utc:
            next_allowed_at = min_next
    end_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_utc = end_local.astimezone(timezone.utc)
    if daily_used >= limit_utils.MANUAL_SOURCE_DAILY_LIMIT and end_utc > now_utc:
        next_allowed_at = max(next_allowed_at or end_utc, end_utc)

    allowed = daily_used < limit_utils.MANUAL_SOURCE_DAILY_LIMIT and (
        next_allowed_at is None or now_utc >= next_allowed_at
    )
    daily_remaining = max(0, limit_utils.MANUAL_SOURCE_DAILY_LIMIT - daily_used)
    return {
        "allowed": allowed,
        "daily_used": daily_used,
        "daily_remaining": daily_remaining,
        "daily_limit": limit_utils.MANUAL_SOURCE_DAILY_LIMIT,
        "min_interval_seconds": limit_utils.MANUAL_MIN_INTERVAL_SECONDS,
        "next_allowed_at": next_allowed_at.isoformat() if next_allowed_at else None,
        "server_time": now_utc.isoformat(),
        "timezone": settings.timezone,
        "count_key": count_key,
        "last_key": last_key,
        "ttl": None,
    }


def _reserve_source_slot(source_id: int) -> None:
    client = _redis_client()
    limit_utils.reserve_source_interval(client, source_id)
    # 按“触发次数”计数
    limit_utils.increment_source_count(client, source_id, 1)


def _update_source_yaml(name: str, updates: dict[str, Any]) -> bool:
    path = Path("config/sources.yaml")
    if not path.exists():
        return False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources", [])
    found = False
    for entry in sources:
        if entry.get("name") != name:
            continue
        if "weight" in updates:
            entry["weight"] = float(updates["weight"])
        if "fetch_interval_minutes" in updates:
            entry["fetch_interval_minutes"] = int(updates["fetch_interval_minutes"])
        if "active" in updates:
            entry["active"] = bool(updates["active"])
        found = True
        break
    if not found:
        return False
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return True


@router.get("/api/feed")
def get_feed(
    topic: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
    favorite: bool | None = None,
    world: str | None = None,
    randomize: bool = True,
    order: str | None = None,
    source: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    limit = min(limit, 100)
    feed_order = _normalize_feed_order(order, randomize)
    world = (world or "real").lower()
    if world != "real":
        raise HTTPException(status_code=400, detail="Invalid world")
    query = (
        db.query(Item)
        .filter(Item.is_disliked.is_(False), Item.world == world)
        .order_by(Item.created_at.desc(), Item.id.desc())
    )
    if source:
        query = query.join(Source, Item.source_id == Source.id)
        if source.isdigit():
            query = query.filter(Source.id == int(source))
        else:
            query = query.filter(Source.name == source)
    if topic == "收藏":
        favorite = True
        topic = None
    if favorite:
        query = query.filter(Item.is_favorite.is_(True))
    if topic:
        query = query.join(ItemTopic).filter(ItemTopic.topic == topic)
    if search:
        keyword = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Item.title_zh.ilike(keyword),
                Item.summary_zh.ilike(keyword),
                Item.title.ilike(keyword),
                Item.excerpt.ilike(keyword),
            )
        )
    feedback_filter_enabled = not favorite and not search and not source
    if cursor:
        ts, item_id = _parse_cursor(cursor)
        query = query.filter(
            (Item.created_at < ts) | ((Item.created_at == ts) & (Item.id < item_id))
        )
        candidate_limit = min(300, max(limit * 3, limit))
        items = query.limit(candidate_limit if feedback_filter_enabled else limit).all()
        if feedback_filter_enabled:
            items = _apply_dislike_feedback(items, limit)[:limit]
    else:
        if feed_order == "random" and not favorite and not search and not source:
            pool_limit = min(200, max(limit * 4, limit))
            pool = query.limit(pool_limit).all()
            pool = _apply_dislike_feedback(pool, max(limit * 2, limit))
            if len(pool) > limit:
                start = random.randint(0, len(pool) - limit)
                items = pool[start : start + limit]
            else:
                items = pool
        else:
            candidate_limit = min(300, max(limit * 3, limit))
            items = query.limit(candidate_limit if feedback_filter_enabled else limit).all()
            if feedback_filter_enabled:
                items = _apply_dislike_feedback(items, limit)[:limit]
    next_cursor = None
    if items:
        last = items[-1]
        next_cursor = f"{last.created_at.isoformat()}|{last.id}"
    return {
        "items": [_serialize_item(item) for item in items],
        "next_cursor": next_cursor,
        "order": feed_order,
    }


@router.get("/api/item/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return _serialize_detail(item)


@router.post("/api/item/{item_id}/favorite")
def set_favorite(
    item_id: int,
    favorite: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.is_favorite = bool(favorite)
    item.favorited_at = datetime.now(timezone.utc) if favorite else None
    db.commit()
    return {"id": item.id, "is_favorite": item.is_favorite, "favorited_at": item.favorited_at}


@router.post("/api/item/{item_id}/dislike")
def set_dislike(
    item_id: int,
    disliked: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    previous = bool(item.is_disliked)
    item.is_disliked = bool(disliked)
    item.disliked_at = datetime.now(timezone.utc) if item.is_disliked else None
    if item.is_disliked:
        # Keep only summary fields for disliked items.
        item.translation_full_zh = None
        item.translation_excerpt = None
        item.excerpt = None
    topics = [topic.topic for topic in item.topics]
    if item.is_disliked and not previous:
        record_dislike_feedback(item.site_name, item.url_canonical or item.url, topics)
    elif previous and not item.is_disliked:
        revert_dislike_feedback(item.site_name, item.url_canonical or item.url, topics)
    db.commit()
    return {"id": item.id, "is_disliked": item.is_disliked, "disliked_at": item.disliked_at}


@router.post("/api/item/{item_id}/view")
def mark_view(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.view_count = (item.view_count or 0) + 1
    item.last_viewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": item.id, "view_count": item.view_count, "last_viewed_at": item.last_viewed_at}


@router.post("/api/item/{item_id}/read")
def mark_read(
    item_id: int,
    seconds: int = Body(0, embed=True),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    safe_seconds = max(0, min(int(seconds), 3600))
    if safe_seconds <= 0:
        return {"id": item.id, "total_read_seconds": item.total_read_seconds}
    item.total_read_seconds = (item.total_read_seconds or 0) + safe_seconds
    if safe_seconds >= LONG_READ_SECONDS:
        item.long_read_count = (item.long_read_count or 0) + 1
    db.commit()
    return {
        "id": item.id,
        "total_read_seconds": item.total_read_seconds,
        "long_read_count": item.long_read_count,
    }


@router.post("/api/ingest/run")
def run_ingest(db: Session = Depends(get_db)):
    limits = _ingest_limits(db)
    if not limits["allowed"]:
        wait_seconds = 0
        if limits["next_allowed_at"]:
            try:
                next_at = datetime.fromisoformat(limits["next_allowed_at"])
                wait_seconds = max(0, int((next_at - datetime.now(timezone.utc)).total_seconds()))
            except Exception:
                wait_seconds = 0
        return JSONResponse(
            status_code=429,
            content={
                "error": "ingest_rate_limited",
                "message": "触发过于频繁，请稍后再试。",
                "limits": limits,
                "wait_seconds": wait_seconds,
            },
            headers={"Retry-After": str(wait_seconds)} if wait_seconds else None,
        )
    _reserve_manual_slot()
    run_id = str(uuid.uuid4())
    run = IngestRun(id=run_id, mode="manual", status="queued")
    db.add(run)
    db.commit()
    result = run_ingest_task.delay("manual", run_id)
    run.celery_task_id = result.id
    db.commit()
    return {"run_id": run_id}


@router.post("/api/ingest/source/{source_id}")
def run_ingest_source(
    source_id: int,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    source_limits = _check_source_limit(source_id)
    if not source_limits["allowed"]:
        wait_seconds = 0
        if source_limits["next_allowed_at"]:
            try:
                next_at = datetime.fromisoformat(source_limits["next_allowed_at"])
                wait_seconds = max(0, int((next_at - datetime.now(timezone.utc)).total_seconds()))
            except Exception:
                wait_seconds = 0
        return JSONResponse(
            status_code=429,
            content={
                "error": "ingest_source_rate_limited",
                "message": "该来源触发过于频繁，请稍后再试。",
                "source_limits": {
                    "daily_limit": source_limits["daily_limit"],
                    "daily_used": source_limits["daily_used"],
                    "daily_remaining": source_limits["daily_remaining"],
                    "min_interval_seconds": source_limits["min_interval_seconds"],
                    "next_allowed_at": source_limits["next_allowed_at"],
                    "server_time": source_limits["server_time"],
                    "timezone": source_limits["timezone"],
                },
                "wait_seconds": wait_seconds,
            },
            headers={"Retry-After": str(wait_seconds)} if wait_seconds else None,
        )

    _reserve_source_slot(source_id)
    run_id = str(uuid.uuid4())
    run = IngestRun(id=run_id, mode="manual", status="queued")
    db.add(run)
    db.commit()
    result = run_ingest_task.delay("manual", run_id, [source.name])
    run.celery_task_id = result.id
    db.commit()
    return {"run_id": run_id, "source": {"id": source.id, "name": source.name}}


@router.get("/api/ingest/status/{run_id}")
def ingest_status(run_id: str, db: Session = Depends(get_db)):
    run = db.query(IngestRun).filter(IngestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _reconcile_cancel_status(run, db)
    return {
        "run_id": run.id,
        "mode": run.mode,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "celery_task_id": run.celery_task_id,
        "cancel_requested_at": run.cancel_requested_at,
        "canceled_at": run.canceled_at,
        "total_candidates": run.total_candidates,
        "new_items": run.new_items,
        "error": run.error,
    }


@router.post("/api/ingest/url")
def ingest_url(payload: dict = Body(...)):
    url = (payload or {}).get("url")
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=400, detail="Missing url")
    try:
        item = ingest_single_url(url.strip())
    except IngestRejectedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": item.id, "url": item.url}




@router.get("/api/ingest/recent")
def ingest_recent(limit: int = 20, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 100)
    runs = (
        db.query(IngestRun)
        .order_by(IngestRun.started_at.desc())
        .limit(limit)
        .all()
    )
    for run in runs:
        _reconcile_cancel_status(run, db)
    return {
        "runs": [
            {
                "run_id": r.id,
                "mode": r.mode,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "celery_task_id": r.celery_task_id,
                "cancel_requested_at": r.cancel_requested_at,
                "canceled_at": r.canceled_at,
                "total_candidates": r.total_candidates,
                "new_items": r.new_items,
                "error": r.error,
            }
            for r in runs
        ]
    }


@router.get("/api/ingest/limits")
def ingest_limits(db: Session = Depends(get_db)):
    return _ingest_limits(db)


@router.post("/api/admin/login")
def admin_login(code: str = Body(..., embed=True), request: Request = None):
    if not settings.admin_totp_secret:
        raise HTTPException(status_code=503, detail="Admin OTP not configured")
    client = _redis_client()
    ip = _get_client_ip(request) if request else "unknown"
    allowed, retry_after = _check_admin_otp_limit(client, ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "otp_rate_limited",
                "message": "OTP 尝试过多，请稍后再试。",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)} if retry_after else None,
        )
    otp = pyotp.TOTP(settings.admin_totp_secret)
    if not otp.verify(code, valid_window=1):
        _record_admin_otp_failure(client, ip)
        raise HTTPException(status_code=401, detail="Invalid OTP")
    _clear_admin_otp_failures(client, ip)
    token = secrets.token_urlsafe(32)
    _store_admin_token(token)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=max(1, settings.admin_session_ttl_hours))
    ).isoformat()
    return {"token": token, "expires_at": expires_at}


@router.get("/api/admin/sources")
def admin_sources(_: None = Depends(_require_admin), db: Session = Depends(get_db)):
    tz = ZoneInfo(settings.timezone)
    today_start_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(timezone.utc)
    rows = (
        db.query(
            Source,
            func.count(Item.id),
            func.sum(case((Item.fetched_at >= today_start_utc, 1), else_=0)),
            func.max(Item.fetched_at),
        )
        .outerjoin(Item, Item.source_id == Source.id)
        .group_by(Source.id)
        .order_by(Source.name.asc())
        .all()
    )
    payload = []
    for source, total_count, today_count, last_item_at in rows:
        payload.append(
            {
                "id": source.id,
                "name": source.name,
                "type": source.type,
                "active": source.active,
                "weight": source.weight,
                "fetch_interval_minutes": source.fetch_interval_minutes,
                "last_fetch_at": source.last_fetch_at.isoformat() if source.last_fetch_at else None,
                "topics": source.topics,
                "config": source.config,
                "items_count": int(total_count or 0),
                "items_today": int(today_count or 0),
                "last_item_at": last_item_at.isoformat() if last_item_at else None,
            }
        )
    return {"sources": payload}


@router.patch("/api/admin/source/{source_id}")
def admin_update_source(
    source_id: int,
    payload: dict[str, Any] = Body(...),
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    updates: dict[str, Any] = {}
    if "weight" in payload:
        updates["weight"] = float(payload["weight"])
        source.weight = updates["weight"]
    if "fetch_interval_minutes" in payload:
        updates["fetch_interval_minutes"] = int(payload["fetch_interval_minutes"])
        source.fetch_interval_minutes = updates["fetch_interval_minutes"]
    if "active" in payload:
        updates["active"] = bool(payload["active"])
        source.active = updates["active"]
    if updates:
        _update_source_yaml(source.name, updates)
    db.commit()
    return {
        "id": source.id,
        "name": source.name,
        "weight": source.weight,
        "fetch_interval_minutes": source.fetch_interval_minutes,
        "active": source.active,
    }


@router.get("/api/admin/ingest/recent")
def admin_ingest_recent(
    limit: int = 20,
    cursor: str | None = None,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    limit = min(max(limit, 1), 100)
    query = db.query(IngestRun).order_by(IngestRun.started_at.desc(), IngestRun.id.desc())
    if cursor:
        ts, run_id = _parse_run_cursor(cursor)
        query = query.filter(
            (IngestRun.started_at < ts)
            | ((IngestRun.started_at == ts) & (IngestRun.id < run_id))
        )
    runs = query.limit(limit).all()
    for run in runs:
        _reconcile_cancel_status(run, db)
    next_cursor = None
    if runs:
        last = runs[-1]
        if last.started_at:
            next_cursor = f"{last.started_at.isoformat()}|{last.id}"
    return {
        "runs": [
            {
                "run_id": r.id,
                "mode": r.mode,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "celery_task_id": r.celery_task_id,
                "cancel_requested_at": r.cancel_requested_at,
                "canceled_at": r.canceled_at,
                "total_candidates": r.total_candidates,
                "new_items": r.new_items,
                "error": r.error,
            }
            for r in runs
        ],
        "next_cursor": next_cursor,
    }


@router.get("/api/admin/ingest/logs/{run_id}")
def admin_ingest_logs(
    run_id: str,
    tail: int = 200,
    _: None = Depends(_require_admin),
):
    tail = min(max(tail, 1), 500)
    path = Path(settings.log_dir) / "ingest" / f"{run_id}.log"
    if not path.exists():
        return {"run_id": run_id, "exists": False, "lines": []}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"run_id": run_id, "exists": False, "lines": []}
    lines = text.splitlines()
    if len(lines) > tail:
        lines = lines[-tail:]
    return {"run_id": run_id, "exists": True, "lines": lines}




@router.post("/api/admin/ingest/cancel/{run_id}")
def admin_ingest_cancel(
    run_id: str,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    run = db.query(IngestRun).filter(IngestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in {"completed", "failed", "canceled"}:
        return {
            "run_id": run.id,
            "status": run.status,
            "message": "任务已结束，无法取消",
        }
    now = datetime.now(timezone.utc)
    if run.status == "queued":
        run.status = "canceled"
        run.canceled_at = now
        run.finished_at = now
    else:
        run.status = "cancel_requested"
        run.cancel_requested_at = now
    db.commit()

    client = _redis_client()
    if client is not None:
        try:
            client.setex(_cancel_key(run_id), CANCEL_KEY_TTL_SECONDS, "1")
        except Exception:
            pass

    if run.celery_task_id:
        try:
            celery_app.control.revoke(run.celery_task_id)
        except Exception:
            pass

    return {"run_id": run.id, "status": run.status}


@router.get("/api/sources/stats")
def source_stats(db: Session = Depends(get_db)):
    tz = ZoneInfo(settings.timezone)
    today_start_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_local.astimezone(timezone.utc)
    rows = (
        db.query(
            Source,
            func.count(Item.id),
            func.sum(case((Item.fetched_at >= today_start_utc, 1), else_=0)),
            func.max(Item.fetched_at),
        )
        .outerjoin(Item, Item.source_id == Source.id)
        .group_by(Source.id)
        .order_by(Source.name.asc())
        .all()
    )
    result = []
    for source, count, today_count, last_item_at in rows:
        result.append(
            {
                "id": source.id,
                "name": source.name,
                "type": source.type,
                "active": source.active,
                "weight": source.weight,
                "fetch_interval_minutes": source.fetch_interval_minutes,
                "last_fetch_at": source.last_fetch_at.isoformat() if source.last_fetch_at else None,
                "items_count": int(count or 0),
                "items_today": int(today_count or 0),
                "last_item_at": last_item_at.isoformat() if last_item_at else None,
            }
        )
    return {"sources": result}


@router.get("/api/analytics/items")
def analytics_items(limit: int = 200, db: Session = Depends(get_db)):
    limit = min(limit, 500)
    items = db.query(Item).order_by(Item.created_at.desc()).limit(limit).all()
    payload = []
    for item in items:
        if item.is_disliked:
            status = "disliked"
        elif item.is_favorite:
            status = "favorite"
        elif (item.total_read_seconds or 0) >= LONG_READ_SECONDS or (item.long_read_count or 0) > 0:
            status = "long_read"
        elif (item.view_count or 0) > 0:
            status = "viewed"
        else:
            status = "unviewed"
        payload.append(
            {
                "id": item.id,
                "url": item.url,
                "title_zh": item.title_zh,
                "summary_zh": item.summary_zh,
                "summary_json": item.summary_json,
                "topics": [t.topic for t in item.topics],
                "is_favorite": item.is_favorite,
                "is_disliked": item.is_disliked,
                "view_count": item.view_count,
                "total_read_seconds": item.total_read_seconds,
                "long_read_count": item.long_read_count,
                "status": status,
                "fetched_at": item.fetched_at,
            }
        )
    return {"items": payload}
