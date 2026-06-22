"""意图分类器测试

LLM 驱动分类（单元测试不调真实 API），降级只测结构完整性。
"""

from enterprise_qa.intent_classifier import (
    LLMIntentClassifier,
    IntentResult,
    QueryType,
    classify_intent,
)


class TestIntentFallback:
    """降级兜底测试——验证返回有效结构"""

    def test_fallback_returns_valid_result(self):
        """降级返回有效的 IntentResult"""
        intent = classify_intent("张三的邮箱是多少？")
        assert isinstance(intent, IntentResult)

    def test_fallback_has_all_fields(self):
        """降级返回完整字段"""
        intent = classify_intent("张三的邮箱是多少？")
        assert hasattr(intent, "query_type")
        assert hasattr(intent, "has_db_intent")
        assert hasattr(intent, "has_kb_intent")
        assert hasattr(intent, "entities")
        assert hasattr(intent, "confidence")
        assert hasattr(intent, "original_question")
        assert hasattr(intent, "reasoning")

    def test_fallback_defaults_to_hybrid(self):
        """降级默认 hybrid"""
        intent = classify_intent("年假怎么算？")
        assert intent.query_type == QueryType.HYBRID
        assert intent.has_db_intent
        assert intent.has_kb_intent

    def test_fallback_preserves_question(self):
        """降级保留原始问题"""
        intent = classify_intent("张三的邮箱是多少？")
        assert intent.original_question == "张三的邮箱是多少？"

    def test_fallback_empty_question(self):
        """空问题返回有效结构"""
        intent = classify_intent("")
        assert isinstance(intent, IntentResult)

    def test_fallback_no_entities(self):
        """降级不做实体提取"""
        intent = classify_intent("张三的邮箱是多少？")
        assert intent.entities == {}


class TestLLMIntentClassifier:
    """LLM 分类器单元测试（不调用真实 API）"""

    def test_parse_db_only(self):
        """解析 LLM 返回的 db_only"""
        classifier = LLMIntentClassifier(api_key="test")
        parsed = classifier._parse_response({
            "query_type": "db_only",
            "has_db_intent": True,
            "has_kb_intent": False,
            "entities": {"person": "张三"},
            "reasoning": "员工信息查询",
            "confidence": 0.95,
        }, "张三的邮箱是多少？")
        assert parsed.query_type == QueryType.DB_ONLY
        assert parsed.has_db_intent
        assert not parsed.has_kb_intent
        assert parsed.entities.get("person") == "张三"

    def test_parse_kb_only(self):
        """解析 LLM 返回的 kb_only"""
        classifier = LLMIntentClassifier(api_key="test")
        parsed = classifier._parse_response({
            "query_type": "kb_only",
            "has_db_intent": False,
            "has_kb_intent": True,
            "entities": {},
            "reasoning": "年假规则查询",
            "confidence": 0.9,
        }, "年假怎么算？")
        assert parsed.query_type == QueryType.KB_ONLY
        assert not parsed.has_db_intent
        assert parsed.has_kb_intent

    def test_parse_hybrid(self):
        """解析 LLM 返回的 hybrid"""
        classifier = LLMIntentClassifier(api_key="test")
        parsed = classifier._parse_response({
            "query_type": "hybrid",
            "has_db_intent": True,
            "has_kb_intent": True,
            "entities": {"person": "王五"},
            "reasoning": "需查绩效、项目数据和晋升规则",
            "confidence": 0.88,
        }, "王五符合晋升条件吗？")
        assert parsed.query_type == QueryType.HYBRID
        assert parsed.entities.get("person") == "王五"

    def test_parse_fuzzy(self):
        """解析 LLM 返回的 fuzzy"""
        classifier = LLMIntentClassifier(api_key="test")
        parsed = classifier._parse_response({
            "query_type": "fuzzy",
            "has_db_intent": True,
            "has_kb_intent": True,
            "entities": {},
            "reasoning": "宽泛问题",
            "confidence": 0.35,
        }, "我们团队最近有什么事？")
        assert parsed.query_type == QueryType.FUZZY

    def test_parse_with_department_entity(self):
        """解析含部门的实体"""
        classifier = LLMIntentClassifier(api_key="test")
        parsed = classifier._parse_response({
            "query_type": "db_only",
            "has_db_intent": True,
            "has_kb_intent": False,
            "entities": {"department": "研发部"},
            "reasoning": "",
            "confidence": 0.8,
        }, "研发部有多少人？")
        assert parsed.entities.get("department") == "研发部"

    def test_no_api_key(self):
        """无 API key 时 classify 返回 None"""
        classifier = LLMIntentClassifier(api_key="")
        assert classifier.classify("test") is None

    def test_prompt_contains_data_sources(self):
        """验证 prompt 包含数据源描述，无硬编码关键词"""
        from enterprise_qa.intent_classifier import _INTENT_PROMPT
        assert "employees" in _INTENT_PROMPT
        assert "hr_policies.md" in _INTENT_PROMPT
        assert "db_only" in _INTENT_PROMPT
        assert "hybrid" in _INTENT_PROMPT
        # 验证没有遗留的硬编码关键词
        assert "张三" not in _INTENT_PROMPT
        assert "考勤" not in _INTENT_PROMPT.split("prompt")[0] if "prompt" in _INTENT_PROMPT else True

    def test_classify_without_llm(self):
        """不传 LLM 分类器时走降级"""
        intent = classify_intent("测试问题")
        assert isinstance(intent, IntentResult)
