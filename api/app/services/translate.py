from __future__ import annotations

import re
from typing import Iterable

import redis
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    return OpenAI(api_key=settings.openai_api_key)


def _redis():
    return redis.Redis.from_url(settings.redis_url)


def _chunk_text(text: str, max_chars: int) -> list[str]:
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush():
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for para in paragraphs:
        if len(para) > max_chars:
            flush()
            for i in range(0, len(para), max_chars):
                chunks.append(para[i : i + max_chars])
            continue

        if not current:
            current = para
            continue

        if len(current) + len(para) + 2 > max_chars:
            flush()
            current = para
        else:
            current = f"{current}\n\n{para}"

    flush()
    return chunks if chunks else [text[:max_chars]]


def _normalize_translation_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in cleaned.split("\n")]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n[ \t]+\n", "\n\n", cleaned)
    # Collapse excessive blank lines from model output.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def cache_translation(item_id: int, text: str) -> None:
    ttl = max(1, settings.translation_ttl_hours) * 3600
    _redis().setex(f"translation:{item_id}", ttl, text)


def get_cached_translation(item_id: int) -> str | None:
    data = _redis().get(f"translation:{item_id}")
    if not data:
        return None
    return data.decode("utf-8")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _translate_chunk(chunk: str) -> str:
    client = _client()
    prompt = (
        "请将下面文本完整翻译为中文（保留专有名词/缩写），"
        "保持原段落结构；如原文已是中文，请原样返回。\n\n"
        f"{chunk}"
    )
    model = settings.translation_model
    kwargs = {}
    if not model.lower().startswith("gpt-5"):
        kwargs["temperature"] = 0.1
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是专业译者，只输出翻译后的纯文本。"},
            {"role": "user", "content": prompt},
        ],
        **kwargs,
    )
    return _normalize_translation_text(resp.choices[0].message.content or "")


def translate_fulltext(text: str) -> str | None:
    if not settings.translate_fulltext:
        return None
    if not text or len(text.strip()) < 80:
        return None
    chunks = _chunk_text(text, settings.translation_chunk_chars)
    translated_parts: list[str] = []
    for chunk in chunks:
        translated_parts.append(_translate_chunk(chunk))
    merged = "\n\n".join(part for part in translated_parts if part)
    return _normalize_translation_text(merged)
