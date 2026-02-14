from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import redis

from app.config import settings

MANUAL_DAILY_LIMIT = 10
MANUAL_MIN_INTERVAL_SECONDS = 300
MANUAL_SOURCE_DAILY_LIMIT = 10


def _day_key(now_local: datetime) -> str:
    return now_local.strftime("%Y%m%d")


def _ttl_until_day_end(now_local: datetime) -> int:
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return max(60, int((end_local - now_local).total_seconds()))


def redis_client() -> redis.Redis | None:
    try:
        return redis.Redis.from_url(settings.redis_url)
    except Exception:
        return None


def limit_keys(now_local: datetime) -> tuple[str, str, int]:
    day_key = _day_key(now_local)
    ttl = _ttl_until_day_end(now_local)
    return f"ingest:manual:{day_key}:count", f"ingest:manual:{day_key}:last", ttl


def source_limit_keys(now_local: datetime, source_id: int) -> tuple[str, str, int]:
    day_key = _day_key(now_local)
    ttl = _ttl_until_day_end(now_local)
    base = f"ingest:manual:{day_key}:source:{source_id}"
    return f"{base}:count", f"{base}:last", ttl


def reserve_manual_interval(client: redis.Redis | None, now_local: datetime | None = None) -> None:
    if client is None:
        return
    tz = ZoneInfo(settings.timezone)
    now_local = now_local or datetime.now(tz)
    _, last_key, ttl = limit_keys(now_local)
    now_ts = datetime.now(timezone.utc).timestamp()
    try:
        client.set(last_key, now_ts, ex=ttl)
    except Exception:
        return


def reserve_source_interval(
    client: redis.Redis | None, source_id: int, now_local: datetime | None = None
) -> None:
    if client is None:
        return
    tz = ZoneInfo(settings.timezone)
    now_local = now_local or datetime.now(tz)
    _, last_key, ttl = source_limit_keys(now_local, source_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    try:
        client.set(last_key, now_ts, ex=ttl)
    except Exception:
        return


def increment_manual_count(
    client: redis.Redis | None, count: int = 1, now_local: datetime | None = None
) -> None:
    if client is None:
        return
    if count <= 0:
        return
    tz = ZoneInfo(settings.timezone)
    now_local = now_local or datetime.now(tz)
    count_key, _, ttl = limit_keys(now_local)
    try:
        pipe = client.pipeline()
        pipe.incrby(count_key, int(count))
        pipe.expire(count_key, ttl)
        pipe.execute()
    except Exception:
        return


def increment_source_count(
    client: redis.Redis | None, source_id: int, count: int, now_local: datetime | None = None
) -> None:
    if client is None:
        return
    if count <= 0:
        return
    tz = ZoneInfo(settings.timezone)
    now_local = now_local or datetime.now(tz)
    count_key, _, ttl = source_limit_keys(now_local, source_id)
    try:
        pipe = client.pipeline()
        pipe.incrby(count_key, int(count))
        pipe.expire(count_key, ttl)
        pipe.execute()
    except Exception:
        return
