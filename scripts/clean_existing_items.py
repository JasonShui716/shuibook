from __future__ import annotations

import argparse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Item
from app.services.extract import extract_article
from app.services.clean import clean_extracted_text
from app.services.translate import translate_fulltext, cache_translation
from app.config import settings


def _should_process(item: Item, only_missing: bool) -> bool:
    if item.world != "real":
        return False
    if only_missing and item.translation_full_zh:
        return False
    return True


def _fetch_item_ids(limit: int | None = None) -> list[int]:
    session: Session = SessionLocal()
    try:
        query = session.query(Item.id).filter(Item.world == "real").order_by(Item.id.asc())
        if limit:
            query = query.limit(limit)
        return [row[0] for row in query.all()]
    finally:
        session.close()


def _process_item(item_id: int, only_missing: bool) -> tuple[int, bool, str | None]:
    session: Session = SessionLocal()
    try:
        item = session.query(Item).filter(Item.id == item_id).first()
        if not item:
            return item_id, False, "not_found"
        if not _should_process(item, only_missing):
            return item_id, False, "skipped"
        url = item.url_canonical or item.url
        if not url:
            return item_id, False, "no_url"
        extract = extract_article(url)
        text = extract.text or ""
        cleaned = clean_extracted_text(
            text,
            title=item.title or item.title_zh,
            url=url,
            site_name=item.site_name,
        )
        if not cleaned:
            return item_id, False, "no_cleaned"
        translation = translate_fulltext(cleaned)
        if translation:
            item.translation_full_zh = translation
            item.translation_excerpt = translation[: settings.excerpt_max_chars]
            cache_translation(item.id, translation)
        item.fetched_at = datetime.now(timezone.utc)
        session.commit()
        return item_id, True, None
    except Exception as exc:
        session.rollback()
        return item_id, False, str(exc)
    finally:
        session.close()


def run(limit: int | None = None, only_missing: bool = False, workers: int = 4) -> None:
    item_ids = _fetch_item_ids(limit)
    total = len(item_ids)
    processed = 0
    skipped = 0
    errors = 0
    if total == 0:
        print("no items to process")
        return

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(_process_item, item_id, only_missing) for item_id in item_ids]
        for idx, future in enumerate(as_completed(futures), start=1):
            item_id, ok, reason = future.result()
            if ok:
                processed += 1
                print(f"[{idx}/{total}] updated item {item_id}")
            else:
                if reason in {"skipped"}:
                    skipped += 1
                else:
                    errors += 1
                    print(f"[{idx}/{total}] error item {item_id}: {reason}")
    print(f"done. updated={processed}, skipped={skipped}, errors={errors}, total={total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run(limit=args.limit, only_missing=args.only_missing, workers=args.workers)
