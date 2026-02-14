from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AppSetting


def get_setting(session: Session, key: str) -> Any | None:
    row = session.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def set_setting(session: Session, key: str, value: Any) -> AppSetting:
    row = session.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        row = AppSetting(key=key, value=value, updated_at=datetime.now(timezone.utc))
        session.add(row)
    else:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    session.commit()
    return row
