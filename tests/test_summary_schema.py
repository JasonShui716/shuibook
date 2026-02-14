import pytest
from app.services.summarize import validate_summary_json


def test_summary_schema_valid():
    payload = {
        "title_zh": "测试标题",
        "summary_zh": "这是一个中文摘要。" * 20,
        "bullets": ["要点1", "要点2"],
        "sentiment": "中性",
        "controversy_points": [],
        "practical_takeaways": ["建议1"],
    }
    obj = validate_summary_json(payload)
    assert obj.title_zh == "测试标题"


def test_summary_schema_missing():
    payload = {"title_zh": "缺字段"}
    with pytest.raises(Exception):
        validate_summary_json(payload)
