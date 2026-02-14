from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

if TYPE_CHECKING:
    from openai import OpenAI


class SummaryPayload(BaseModel):
    title_zh: str
    summary_zh: str
    full_content_zh: str | None = None
    bullets: list[str]
    key_facts: list[str] = Field(default_factory=list)
    sentiment: str
    controversy_points: list[str]
    practical_takeaways: list[str]
    information_gaps: list[str] = Field(default_factory=list)
    signal_level: str | None = None
    what_happened_zh: str | None = None
    why_it_matters_zh: str | None = None
    disclaimer_zh: str | None = None

    @field_validator(
        "bullets",
        "key_facts",
        "controversy_points",
        "practical_takeaways",
        "information_gaps",
    )
    @classmethod
    def ensure_list(cls, value: list[str]) -> list[str]:
        return value or []

    @field_validator("signal_level")
    @classmethod
    def normalize_signal_level(cls, value: str | None) -> str | None:
        if value is None:
            return None
        level = value.strip().lower()
        if level in {"high", "medium", "low"}:
            return level
        return None


class DiscussionPayload(BaseModel):
    consensus_zh: str
    disagreements_zh: str | None = None


def validate_summary_json(data: dict[str, Any]) -> SummaryPayload:
    return SummaryPayload.model_validate(data)


def _client() -> OpenAI:
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError("openai package 未安装") from exc
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    return OpenAI(api_key=settings.openai_api_key)


def _safe_json_loads(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(content[start : end + 1])
        raise


def _build_prompt(text: str, title: str | None, topic_tags: list[str]) -> str:
    topic_str = ", ".join(topic_tags)
    parenting = any("育儿" in t or "婴幼儿" in t or "parent" in t for t in topic_tags)
    disclaimer = "若涉及育儿/健康，请加入非医疗建议免责声明。" if parenting else ""
    return (
        "你是“精读导向”的中文信息分析助手，只能基于给定内容，不得编造。"
        "输出 JSON，且必须包含字段: "
        "title_zh, summary_zh, bullets, key_facts, sentiment, controversy_points, "
        "practical_takeaways, what_happened_zh, why_it_matters_zh, information_gaps, signal_level。"
        "signal_level 只能是 high/medium/low。"
        "summary_zh 目标 450-850 字，必须覆盖“发生了什么 + 核心机制 + 影响范围 + 不确定性”。"
        "what_happened_zh 与 why_it_matters_zh 各至少 80 字。"
        "bullets 4-6 条，每条是具体事实或结论，不要空话。"
        "key_facts 至少 3 条，优先写数字、时间、组织名、产品名、政策名等可验证细节。"
        "高信号（high/medium）必须至少提供 2 条带数字/时间/实体名的可核验事实。"
        "禁止把大段逐句翻译当作摘要，禁止复读原文句子，禁止“主要介绍了/值得关注”这类空泛句式。"
        "practical_takeaways 2-4 条，必须是可执行建议。"
        "若原文信息不足、偏营销、主要是站点模板/验证页、论坛灌水、低质量全文翻译、或缺乏关键事实："
        "将 signal_level 设为 low，information_gaps 写明缺失点，"
        "summary_zh 固定写“信息量不足，建议跳过。”，其余字段可留空列表。"
        "不要复述标题。"
        f"主题: {topic_str}。{disclaimer}\n"
        "内容如下:\n"
        f"标题: {title or ''}\n"
        f"正文: {text}\n"
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def summarize_article(text: str, title: str | None, topic_tags: list[str]) -> SummaryPayload:
    client = _client()
    prompt = _build_prompt(text, title, topic_tags)
    model = settings.openai_model
    kwargs = {}
    if not model.lower().startswith("gpt-5"):
        kwargs["temperature"] = 0.2

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "只输出 JSON，不要额外文字；严格按字段与低信号规则执行。"},
            {"role": "user", "content": prompt},
        ],
        **kwargs,
    )

    content = resp.choices[0].message.content or ""
    data = _safe_json_loads(content)
    return validate_summary_json(data)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def summarize_discussion(comments: list[str]) -> DiscussionPayload:
    client = _client()
    content = "\n".join(comments)
    prompt = (
        "你是中文讨论总结助手。请基于评论内容，给出共识与分歧。"
        "输出 JSON，字段: consensus_zh, disagreements_zh。不要编造。\n"
        f"评论:\n{content}"
    )

    model = settings.openai_model
    kwargs = {}
    if not model.lower().startswith("gpt-5"):
        kwargs["temperature"] = 0.2

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "只输出 JSON，不要额外文字。"},
            {"role": "user", "content": prompt},
        ],
        **kwargs,
    )

    data = _safe_json_loads(resp.choices[0].message.content or "{}")
    try:
        return DiscussionPayload.model_validate(data)
    except ValidationError:
        return DiscussionPayload(consensus_zh="", disagreements_zh=None)
