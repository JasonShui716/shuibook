from app.services.quality import (
    has_substantive_text,
    is_access_challenge_text,
    is_high_signal_summary,
    is_low_signal_url,
)
from types import SimpleNamespace


def test_access_challenge_text_detected():
    assert is_access_challenge_text("Just a moment... verify you are human") is True
    assert is_access_challenge_text("正常文章正文，没有验证页面提示") is False


def test_low_signal_url_detection():
    assert is_low_signal_url("https://www.v2ex.com/t/123456", filter_forum_sources=True) is True
    assert (
        is_low_signal_url(
            "https://github.com/example/repo/pull/42", filter_forum_sources=True
        )
        is True
    )
    assert is_low_signal_url("https://openai.com/index/new-release", filter_forum_sources=True) is False


def test_has_substantive_text_requires_length_and_structure():
    short_text = "这是一段很短的内容。"
    assert has_substantive_text(short_text, min_chars=200, min_paragraphs=2) is False

    long_text = "\n\n".join(
        [
            "第一段描述 2026 年 2 月项目上线背景，包含机构名称、预算区间、时间线、关键里程碑、部署环境、评估口径和失败样本。第一段补充团队分工与上线前准备清单。",
            "第二段说明方案机制、约束条件、指标变化、对比基线、样本覆盖、异常处理、回滚策略、人工复核流程和安全边界。第二段补充监控告警、误报处理与审计记录。",
            "第三段给出业务影响、组织协同成本、后续迭代计划、风险提示、适用场景与不适用场景，并补充可执行落地建议。第三段补充分阶段目标、里程碑和退出条件。",
        ]
    )
    assert has_substantive_text(long_text, min_chars=200, min_paragraphs=2) is True


def test_summary_quality_gate():
    good = SimpleNamespace(
        summary_zh="这是一段详细摘要，包含事件背景、关键事实、影响边界和不确定性，并明确指出上线时间、负责人、适用场景、失败样本和后续迭代计划。" * 12,
        bullets=["事实一：给出明确时间线和主体", "事实二：解释机制与限制条件", "事实三：列出影响对象和规模"],
        practical_takeaways=["先在单一场景灰度验证", "建立失败回滚和人工复核机制"],
        what_happened_zh="某机构发布了新方案，并在真实环境给出了阶段性结果，披露了时间、数据、负责人和明确边界条件。",
        why_it_matters_zh="它影响现有流程的成本结构和实施路径，短期可用于提效，中长期会改变团队分工与风险控制方式。",
        signal_level="high",
    )
    assert is_high_signal_summary(good, min_summary_chars=320, min_bullets=3, min_takeaways=2) is True

    bad = SimpleNamespace(
        summary_zh="信息量不足，建议跳过",
        bullets=[],
        practical_takeaways=[],
        what_happened_zh="",
        why_it_matters_zh="",
        signal_level="low",
    )
    assert is_high_signal_summary(bad, min_summary_chars=320, min_bullets=3, min_takeaways=2) is False
