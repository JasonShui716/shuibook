from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db.session import SessionLocal
from app.db.models import Item


def cleanup_old_items() -> int:
    session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, settings.retention_days))
        items = (
            session.query(Item)
            .filter(Item.is_favorite.is_(False), Item.fetched_at < cutoff)
            .all()
        )
        count = len(items)
        for item in items:
            session.delete(item)
        session.commit()
        return count
    finally:
        session.close()
