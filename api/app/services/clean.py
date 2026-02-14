from __future__ import annotations

from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    return OpenAI(api_key=settings.openai_api_key)


def _truncate(text: str) -> str:
    if not text:
        return ""
    limit = max(500, settings.clean_max_chars)
    cleaned = text.strip()
    if len(cleaned) > limit:
        return cleaned[:limit]
    return cleaned


def _build_prompt(text: str, title: str | None, url: str | None, site_name: str | None) -> str:
    meta: list[str] = []
    if title:
        meta.append(f"标题：{title}")
    if site_name:
        meta.append(f"网站：{site_name}")
    if url:
        meta.append(f"URL：{url}")
    meta_block = "\n".join(meta)
    return (
        "你是网页正文清洗助手。请删除导航栏、页脚、侧边栏、推荐/订阅/广告、"
        "登录提示、版权声明、社交按钮、免责声明、相关文章列表等模板内容，"
        "只保留与文章/帖子主题直接相关的正文段落。\n"
        "保持原有段落结构与顺序；如正文中包含列表/编号，请保留；"
        "不要添加新信息，不要总结，不要改写语气。\n"
        "只输出清洗后的正文纯文本，不要输出标题或说明。\n"
        f"{meta_block}\n"
        "正文：\n"
        f"{text}\n"
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _clean_with_llm(text: str, title: str | None, url: str | None, site_name: str | None) -> str:
    client = _client()
    prompt = _build_prompt(text, title, url, site_name)
    model = settings.clean_model
    kwargs: dict[str, Any] = {}
    if not model.lower().startswith("gpt-5"):
        kwargs["temperature"] = 0.1
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "只输出清洗后的正文，不要额外说明。"},
            {"role": "user", "content": prompt},
        ],
        **kwargs,
    )
    return (resp.choices[0].message.content or "").strip()


def clean_extracted_text(
    text: str | None,
    title: str | None = None,
    url: str | None = None,
    site_name: str | None = None,
) -> str | None:
    if not text:
        return None
    original = text.strip()
    if len(original) < 120:
        return original
    truncated = _truncate(original)
    try:
        cleaned = _clean_with_llm(truncated, title, url, site_name)
    except Exception:
        return original
    if not cleaned:
        return original
    # Avoid over-cleaning; if cleaned text is too short, fallback.
    if len(cleaned) < min(200, int(len(truncated) * 0.2)):
        return original
    return cleaned
