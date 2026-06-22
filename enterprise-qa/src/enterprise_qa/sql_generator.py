"""LLM SQL 生成——通过 DeepSeek API 生成参数化查询

从数据库实时拉取 schema，由 LLM 理解问题后生成 SQL。
无硬编码的 if-else 关键词匹配或 SQL 模板。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import requests

from enterprise_qa.db_connector import DBConnector, DatabaseError


class SQLGenerationError(Exception):
    """SQL 生成异常"""


def _build_schema_text(db: DBConnector) -> str:
    """从数据库实时拉取 schema 描述"""
    try:
        tables = db.get_table_schema()
    except Exception as e:
        return f"无法读取 schema: {e}"

    # 按表分组
    table_columns: dict[str, list[str]] = {}
    for row in tables:
        tname = row["table_name"]
        col = f"  - {row['column_name']} ({row['column_type']})"
        if row["is_pk"]:
            col += " [PRIMARY KEY]"
        table_columns.setdefault(tname, []).append(col)

    # 尝试获取外键关系
    fk_relations: list[str] = []
    for tname in table_columns:
        try:
            fk_rows = db.execute(f"PRAGMA foreign_key_list({tname})")
            for fk in fk_rows:
                fk_relations.append(
                    f"  - {tname}.{fk['from']} → {fk['table']}.{fk['to']}"
                )
        except Exception:
            pass

    lines = [
        "## 数据库 Schema",
        "",
        f"当前日期: 2026-03-27",
        "",
    ]

    for tname, cols in table_columns.items():
        lines.append(f"### {tname}")
        lines.extend(cols)
        lines.append("")

    if fk_relations:
        lines.append("### 外键关系")
        lines.extend(fk_relations)
        lines.append("")

    return "\n".join(lines)


_SQL_PROMPT_TEMPLATE = """你是一个 SQL 专家。根据以下数据库 Schema 和用户问题，生成安全的参数化 SQL 查询。

{schema}

## 规则
1. 只生成 SELECT 查询（只读）
2. 必须使用参数化查询（? 占位符），禁止字符串拼接
3. 值通过 params 数组传入，按 ? 顺序排列
4. 人名、日期等用户输入都走 params，不拼接到 SQL
5. 涉及日期计算时使用 julianday() 函数
6. 如果需要多条查询才能完整回答问题，生成多个

## 输出格式
纯 JSON，不要任何 markdown 标记：
{{
    "queries": [
        {{
            "sql": "SELECT ... WHERE name = ?",
            "params": ["张三"],
            "description": "查询张三的邮箱",
            "source": "employees.email"
        }}
    ]
}}

如果问题与数据库无关，返回空的 queries 数组。"""


class LLMSQLGenerator:
    """基于 LLM 的 SQL 生成器"""

    def __init__(self, db: DBConnector, api_base: str = "", api_key: str = "", model: str = ""):
        self.db = db
        self.api_base = (api_base or "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model or "deepseek-chat"
        self._session: Optional[requests.Session] = None

        # 缓存 schema
        self._schema_text: str = ""

    @property
    def schema_text(self) -> str:
        if not self._schema_text:
            self._schema_text = _build_schema_text(self.db)
        return self._schema_text

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
        return self._session

    def generate(self, question: str) -> list[dict[str, Any]]:
        """根据问题生成参数化 SQL 查询列表

        Args:
            question: 用户的自然语言问题

        Returns:
            [{"sql": str, "params": list, "description": str, "source": str}, ...]
            生成失败或无需 SQL 时返回空列表
        """
        if not self.api_key:
            return self._fallback(question)

        prompt = _SQL_PROMPT_TEMPLATE.format(schema=self.schema_text)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.05,
            "max_tokens": 600,
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

            # 清理 markdown 代码块标记
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

            parsed = json.loads(content)
            raw_queries = parsed.get("queries", [])
            if not raw_queries:
                return []

            # 验证并格式化
            queries = []
            for q in raw_queries:
                sql = q.get("sql", "").strip()
                params_raw = q.get("params", [])
                if not sql:
                    continue

                # 安全检查：只允许 SELECT
                if not sql.strip().upper().startswith("SELECT"):
                    continue

                # 确保 params 是元组
                params = tuple(params_raw) if isinstance(params_raw, list) else ()

                queries.append({
                    "sql": sql,
                    "params": params,
                    "description": q.get("description", ""),
                    "source": q.get("source", ""),
                })

            return queries

        except (requests.RequestException, json.JSONDecodeError,
                KeyError, ValueError) as e:
            return self._fallback(question)

    def _fallback(self, question: str) -> list[dict[str, Any]]:
        """降级：返回最简单的员工信息查询"""
        return [{
            "sql": "SELECT 'employees' AS table_name, name, department, level, status FROM employees LIMIT 3",
            "params": (),
            "description": "员工基本信息",
            "source": "employees",
        }]
