from __future__ import annotations

import redis
import httpx

from app.config import settings


_TOKEN_KEY = "producthunt:token"


def get_producthunt_token() -> str | None:
    if settings.producthunt_token:
        return settings.producthunt_token
    if not (settings.producthunt_key and settings.producthunt_secret):
        return None

    r = redis.Redis.from_url(settings.redis_url)
    cached = r.get(_TOKEN_KEY)
    if cached:
        return cached.decode("utf-8")

    data = {
        "client_id": settings.producthunt_key,
        "client_secret": settings.producthunt_secret,
        "grant_type": "client_credentials",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post("https://api.producthunt.com/v2/oauth/token", data=data)
            if resp.status_code >= 400:
                return None
            payload = resp.json()
    except Exception:
        return None

    token = payload.get("access_token")
    if not token:
        return None

    expires_in = int(payload.get("expires_in") or 3600)
    ttl = max(300, min(expires_in - 60, 24 * 3600))
    r.setex(_TOKEN_KEY, ttl, token)
    return token
