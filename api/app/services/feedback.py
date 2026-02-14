from __future__ import annotations

import re
from urllib.parse import urlparse

import redis

from app.config import settings

DISLIKE_SIGNAL_TTL_SECONDS = 120 * 24 * 3600
SITE_HARD_SUPPRESS_THRESHOLD = 8
SITE_SOFT_SUPPRESS_THRESHOLD = 5

_REDIS_CLIENT: redis.Redis | None = None
_REDIS_INITIALIZED = False


def _redis_client() -> redis.Redis | None:
    global _REDIS_CLIENT, _REDIS_INITIALIZED
    if _REDIS_INITIALIZED:
        return _REDIS_CLIENT
    _REDIS_INITIALIZED = True
    try:
        _REDIS_CLIENT = redis.Redis.from_url(settings.redis_url)
    except Exception:
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def _normalize_token(value: str | None) -> str:
    if not value:
        return ""
    token = value.strip().lower()
    token = re.sub(r"^https?://", "", token)
    token = token.strip("/")
    token = re.sub(r"\s+", "_", token)
    token = re.sub(r"[^a-z0-9._\-\u4e00-\u9fff]", "", token)
    return token


def _site_token(site_name: str | None, url: str | None) -> str:
    if url:
        host = (urlparse(url).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        host = host.split(":", 1)[0]
        host = _normalize_token(host)
        if host:
            return host
    return _normalize_token(site_name)


def _topic_tokens(topics: list[str] | None) -> list[str]:
    if not topics:
        return []
    normalized: list[str] = []
    used: set[str] = set()
    for topic in topics:
        token = _normalize_token(topic)
        if not token or token in used:
            continue
        used.add(token)
        normalized.append(token)
        if len(normalized) >= 3:
            break
    return normalized


def _site_key(token: str) -> str:
    return f"feedback:dislike:site:{token}"


def _topic_key(token: str) -> str:
    return f"feedback:dislike:topic:{token}"


def _to_int(raw: bytes | str | None) -> int:
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except Exception:
        return 0


def _calc_penalty(site_count: int, topic_counts: list[int]) -> float:
    site_penalty = min(3.2, site_count * 0.35)
    topic_penalty = 0.0
    for count in sorted(topic_counts, reverse=True)[:2]:
        topic_penalty += min(1.0, count * 0.2)
    return min(4.0, site_penalty + topic_penalty)


def _signal_counts(
    site_name: str | None,
    url: str | None,
    topics: list[str] | None,
    client: redis.Redis,
) -> tuple[int, list[int]]:
    site_token = _site_token(site_name, url)
    topic_tokens = _topic_tokens(topics)
    keys: list[str] = []
    if site_token:
        keys.append(_site_key(site_token))
    keys.extend(_topic_key(token) for token in topic_tokens)
    if not keys:
        return 0, []
    try:
        values = client.mget(keys)
    except Exception:
        return 0, []
    ints = [_to_int(value) for value in values]
    site_count = ints[0] if site_token else 0
    topic_counts = ints[1:] if site_token else ints
    return site_count, topic_counts


def feedback_penalty_score(
    site_name: str | None,
    url: str | None,
    topics: list[str] | None,
) -> float:
    client = _redis_client()
    if client is None:
        return 0.0
    site_count, topic_counts = _signal_counts(site_name, url, topics, client)
    return _calc_penalty(site_count, topic_counts)


def should_skip_candidate(
    site_name: str | None,
    url: str | None,
    topics: list[str] | None,
) -> bool:
    client = _redis_client()
    if client is None:
        return False
    site_count, topic_counts = _signal_counts(site_name, url, topics, client)
    topic_peak = max(topic_counts) if topic_counts else 0
    if site_count >= SITE_HARD_SUPPRESS_THRESHOLD:
        return True
    if site_count >= SITE_SOFT_SUPPRESS_THRESHOLD and topic_peak >= 4:
        return True
    return False


def batch_feedback_penalties(
    records: list[tuple[str | None, str | None, list[str]]],
) -> list[float]:
    if not records:
        return []
    client = _redis_client()
    if client is None:
        return [0.0] * len(records)

    resolved: list[tuple[str | None, list[str]]] = []
    unique_keys: list[str] = []
    seen_keys: set[str] = set()

    for site_name, url, topics in records:
        site_token = _site_token(site_name, url)
        topic_tokens = _topic_tokens(topics)
        site_key = _site_key(site_token) if site_token else None
        topic_keys = [_topic_key(token) for token in topic_tokens]
        resolved.append((site_key, topic_keys))
        for key in [site_key, *topic_keys]:
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            unique_keys.append(key)

    if not unique_keys:
        return [0.0] * len(records)

    try:
        values = client.mget(unique_keys)
    except Exception:
        return [0.0] * len(records)

    value_map = {key: _to_int(value) for key, value in zip(unique_keys, values)}
    penalties: list[float] = []
    for site_key, topic_keys in resolved:
        site_count = value_map.get(site_key, 0) if site_key else 0
        topic_counts = [value_map.get(key, 0) for key in topic_keys]
        penalties.append(_calc_penalty(site_count, topic_counts))
    return penalties


def record_dislike_feedback(
    site_name: str | None,
    url: str | None,
    topics: list[str] | None,
) -> None:
    client = _redis_client()
    if client is None:
        return
    site_token = _site_token(site_name, url)
    topic_tokens = _topic_tokens(topics)
    keys: set[str] = set()
    if site_token:
        keys.add(_site_key(site_token))
    keys.update(_topic_key(token) for token in topic_tokens)
    for key in keys:
        try:
            client.incr(key, 1)
            client.expire(key, DISLIKE_SIGNAL_TTL_SECONDS)
        except Exception:
            continue


def revert_dislike_feedback(
    site_name: str | None,
    url: str | None,
    topics: list[str] | None,
) -> None:
    client = _redis_client()
    if client is None:
        return
    site_token = _site_token(site_name, url)
    topic_tokens = _topic_tokens(topics)
    keys: set[str] = set()
    if site_token:
        keys.add(_site_key(site_token))
    keys.update(_topic_key(token) for token in topic_tokens)
    for key in keys:
        try:
            value = client.decr(key, 1)
            if value < 0:
                client.set(key, 0)
            client.expire(key, DISLIKE_SIGNAL_TTL_SECONDS)
        except Exception:
            continue
