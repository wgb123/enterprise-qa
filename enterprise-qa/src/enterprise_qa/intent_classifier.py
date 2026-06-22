"""意图分类器——LLM 驱动 + 保守兜底

LLM 通过系统 prompt 了解数据源结构（DB schema + KB 文档列表），
自行判断问题类型、提取实体。降级时不依赖任何直觉关键词或名单。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import requests


class QueryType(str, Enum):
    DB_ONLY = "db_only"          # 纯数据库查询
    KB_ONLY = "kb_only"          # 纯知识库查询
    HYBRID = "hybrid"            # 混合查询（DB + KB）
    FUZZY = "fuzzy"              # 模糊语义查询


@dataclass
class IntentResult:
    query_type: QueryType = QueryType.HYBRID  # 降级默认 hybrid（两边都查）
    has_db_intent: bool = True
    has_kb_intent: bool = True
    entities: dict[str, str] = field(default_factory=dict)
    original_question: str = ""
    reasoning: str = ""
    confidence: float = 0.0


# ============================================================
# LLM 意图分类 prompt
# ============================================================

_INTENT_PROMPT = """你是一个企业智能问答系统的意图分析专家。你的任务是对用户的问题进行分类，输出 JSON。

## 可查询的数据源

### 数据库（结构化数据）
- employees: 员工信息（employee_id, name, department, level, hire_date, manager_id, email, status）
- projects: 项目记录（project_id, name, lead_id, status, start_date, end_date, budget）
- project_members: 项目成员（project_id, employee_id, role, join_date）
- attendance: 考勤（employee_id, date, status）
- performance_reviews: 绩效考核（employee_id, year, quarter, kpi_score, grade）

### 知识库文档（非结构化文档）
- hr_policies.md: 人事制度（考勤、请假、加班）
- promotion_rules.md: 晋升评定标准
- tech_docs.md: 技术规范
- finance_rules.md: 财务报销制度
- faq.md: 常见问题
- meeting_notes/: 会议纪要

## 问题类型定义
- db_only: 问题只需要查询数据库中的结构化数据（员工信息、项目记录、考勤、绩效等具体数字和记录）
- kb_only: 问题只需要查询知识库文档中的制度、规则、政策（制度怎么规定、规则是什么）
- hybrid: 问题需要同时查询数据库和知识库才能完整回答（如"某人是否符合晋升条件"——需要查该人的DB记录+晋升规则）
- fuzzy: 问题宽泛模糊，没有明确查询目标（如"我们团队最近有什么事"）

## 实体提取
从问题中提取以下实体（没有则留空字符串）：
- person: 员工姓名
- department: 部门名称
- project: 项目名称
- time_range: 时间范围（如"上个月"、"今年"）

## 输出格式
只输出纯 JSON，不要任何 markdown 标记：
{
    "query_type": "db_only|kb_only|hybrid|fuzzy",
    "has_db_intent": true/false,
    "has_kb_intent": true/false,
    "entities": {"person": "", "department": "", "project": "", "time_range": ""},
    "reasoning": "简要说明判断依据",
    "confidence": 0.0-1.0
}"""


# ============================================================
# LLM 意图分类器
# ============================================================

class LLMIntentClassifier:
    """基于 LLM 的意图分类器"""

    def __init__(self, api_base: str = "", api_key: str = "", model: str = ""):
        self.api_base = (api_base or "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model or "deepseek-chat"
        self._session: Optional[requests.Session] = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
        return self._session

    def classify(self, question: str) -> Optional[IntentResult]:
        """调用 LLM 分类"""
        if not self.api_key:
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _INTENT_PROMPT},
                {"role": "user", "content": question},
            ],
            "temperature": 0.1,
            "max_tokens": 300,
        }

        try:
            resp = self.session.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # 去除可能的 markdown 代码块标记
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

            parsed = json.loads(content)
            return self._parse_response(parsed, question)

        except (requests.RequestException, json.JSONDecodeError,
                KeyError, ValueError) as e:
            return None

    def _parse_response(self, parsed: dict, question: str) -> IntentResult:
        """解析 LLM 返回的 JSON"""
        qt_str = parsed.get("query_type", "fuzzy")
        try:
            query_type = QueryType(qt_str)
        except ValueError:
            query_type = QueryType.FUZZY

        entities = {}
        raw_entities = parsed.get("entities", {}) or {}
        for key in ("person", "department", "project", "time_range"):
            val = raw_entities.get(key, "")
            if val and isinstance(val, str):
                entities[key] = val

        return IntentResult(
            query_type=query_type,
            has_db_intent=bool(parsed.get("has_db_intent", False)),
            has_kb_intent=bool(parsed.get("has_kb_intent", False)),
            entities=entities,
            original_question=question,
            reasoning=parsed.get("reasoning", ""),
            confidence=float(parsed.get("confidence", 0.5)),
        )


# ============================================================
# 保守兜底（LLM 不可用时——不依赖任何关键词或名单）
# ============================================================

def _rule_based_classify(question: str) -> IntentResult:
    """保守兜底：没有 LLM 时默认 hybrid，两边都查

    不做任何实体提取、关键词匹配或模式识别。
    依赖 LLM 做理解，降级时只保证不遗漏信息。
    """
    result = IntentResult(original_question=question.strip())
    result.query_type = QueryType.HYBRID
    result.has_db_intent = True
    result.has_kb_intent = True
    result.confidence = 0.3
    return result


# ============================================================
# 统一入口
# ============================================================

def classify_intent(question: str, llm_classifier: Optional[LLMIntentClassifier] = None) -> IntentResult:
    """意图分类统一入口

    1. 优先 LLM（接到 DeepSeek API，prompt 里描述了完整数据源）
    2. LLM 不可用时降级到保守兜底（默认 hybrid，两边都查）
    """
    if llm_classifier:
        result = llm_classifier.classify(question)
        if result:
            return result

    return _rule_based_classify(question)
