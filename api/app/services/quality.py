from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ACCESS_CHALLENGE_MARKERS = (
    "just a moment",
    "attention required",
    "cf-browser-verification",
    "cf-chl",
    "challenge-platform",
    "enable javascript",
    "verify you are human",
    "security check",
    "access denied",
    "ddos protection",
    "检测到异常流量",
    "请完成验证",
    "安全验证",
    "人机验证",
    "访问受限",
)

GENERIC_SUMMARY_MARKERS = (
    "信息量不足，建议跳过",
    "原文信息不足",
    "无法提炼出关键事实",
    "建议直接阅读原文",
    "主要介绍了",
    "值得关注",
)

LOW_SIGNAL_HOSTS = {
    "linux.do",
    "v2ex.com",
    "www.v2ex.com",
}

NON_ARTICLE_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".zip",
    ".rar",
    ".7z",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
}


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def is_access_challenge_text(text: str | None) -> bool:
    lower = normalize_text(text).lower()
    if not lower:
        return False
    sample = lower[:30000]
    return any(marker in sample for marker in ACCESS_CHALLENGE_MARKERS)


def is_low_signal_url(url: str, filter_forum_sources: bool = True) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()

    if filter_forum_sources and (host in LOW_SIGNAL_HOSTS or host.endswith(".v2ex.com")):
        return True

    if host.endswith("youtube.com") or host == "youtu.be":
        return True

    if host == "github.com" and any(
        token in path
        for token in (
            "/pull/",
            "/commit/",
            "/issues/",
            "/compare/",
            "/releases/tag/",
        )
    ):
        return True

    ext = Path(path).suffix.lower()
    if ext and ext in NON_ARTICLE_EXTENSIONS:
        return True

    return False


def has_substantive_text(text: str | None, min_chars: int, min_paragraphs: int) -> bool:
    raw = (text or "").strip()
    if len(raw) < max(80, min_chars):
        return False
    if is_access_challenge_text(raw):
        return False

    paragraphs = [p.strip() for p in re.split(r"\n{2,}|\r\n\r\n", raw) if p.strip()]
    long_paragraphs = [p for p in paragraphs if len(p) >= 40]
    if len(long_paragraphs) < max(1, min_paragraphs):
        return False

    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", raw))
    if cjk_chars >= max(80, min_chars // 2):
        return True

    tokens = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", raw.lower())
    if len(tokens) < 60:
        return False

    unique_ratio = len(set(tokens)) / max(1, len(tokens))
    if unique_ratio < 0.08:
        return False

    return True


def is_high_signal_summary(
    summary: Any,
    min_summary_chars: int,
    min_bullets: int,
    min_takeaways: int,
) -> bool:
    summary_text = normalize_text(getattr(summary, "summary_zh", ""))
    if len(summary_text) < max(80, min_summary_chars):
        return False

    if any(marker in summary_text for marker in GENERIC_SUMMARY_MARKERS):
        return False

    bullets = [
        normalize_text(item)
        for item in getattr(summary, "bullets", [])
        if normalize_text(item)
    ]
    takeaways = [
        normalize_text(item)
        for item in getattr(summary, "practical_takeaways", [])
        if normalize_text(item)
    ]

    if len(bullets) < max(1, min_bullets):
        return False
    if len(takeaways) < max(1, min_takeaways):
        return False

    what_happened = normalize_text(getattr(summary, "what_happened_zh", ""))
    why_matters = normalize_text(getattr(summary, "why_it_matters_zh", ""))
    if len(what_happened) < 40:
        return False
    if len(why_matters) < 40:
        return False

    signal_level = normalize_text(getattr(summary, "signal_level", "")).lower()
    if signal_level == "low":
        return False

    return True
