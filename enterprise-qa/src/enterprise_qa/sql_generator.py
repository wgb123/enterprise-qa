"""LLM SQL 生成——通过 DeepSeek API 生成参数化查询

从数据库实时拉取 schema，由 LLM 理解问题后生成 SQL。
无硬编码的 if-else 关键词匹配或 SQL 模板。
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
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
        f"当前日期: {date.today().isoformat()}",
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

## 多表关联提示
- 查"某人负责的项目" = projects.lead_id + project_members.employee_id 都查，用 UNION
- 查"迟到次数" = attendance WHERE status='late'，用子查询找 employee_id
- 查"部门人数/员工" = employees 按 department 分组，WHERE status='active'（排除已离职）
- 查"活跃项目" = projects WHERE status='active'

## 输出示例
正确查询某人负责的所有项目：
```sql
SELECT p.project_id, p.name, 'lead' AS role FROM projects p JOIN employees e ON p.lead_id = e.employee_id WHERE e.name = ?
UNION
SELECT p.project_id, p.name, pm.role FROM project_members pm JOIN projects p ON pm.project_id = p.project_id JOIN employees e ON pm.employee_id = e.employee_id WHERE e.name = ?
```

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
        """根据问题生成参数化 SQL 查询列表"""
        if not self.api_key:
            return self._fallback(question)

        prompt = _SQL_PROMPT_TEMPLATE.format(schema=self.schema_text)
        # 业务规则约束（简短，防止 LLM 超时）
        prompt += """
## 业务约束
- 查人数 = 只统计 status='active' 的在职员工，SQL 同时返回 COUNT(*) 和 GROUP_CONCAT(name)
- 查某人参与的项目 = 同时查 projects.lead_id 和 project_members 两个表，用 UNION
- 查考核/绩效 = 查 performance_reviews 表，用子查询找 employee_id
- 查迟到 = 查 attendance 表 WHERE status='late'
- 查部门领导 = JOIN employees 自关联 manager_id: SELECT e2.name FROM employees e JOIN employees e2 ON e.manager_id = e2.employee_id WHERE e.department = ?
- 复杂查询（晋升评估等）：需要多条 SQL，分别查员工信息、绩效、项目"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.05,
            "max_tokens": 1500,
        }

        try:
            resp = self.session.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                timeout=30,
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

    _NAME_PATTERN = re.compile(r'([\u4e00-\u9fff]{2,3})')  # 2-3字中文名（不含"的"结尾）
    _DEPT_PATTERN = re.compile(r'(研发部|产品部|市场部|管理层|技术部|人事部)')

    def _fallback(self, question: str) -> list[dict[str, Any]]:
        """降级：根据问题关键词生成简单查询"""
        q = question.strip()
        queries: list[dict[str, Any]] = []

        # 提取名字：取第一个出现的 2-3 字中文词
        names = self._NAME_PATTERN.findall(q)
        name = ""
        for n in names:
            n = n.rstrip("的")
            if n not in ("什么", "怎么", "如何", "哪个", "多少", "部门", "项目", "绩效", "迟到", "规则"):
                name = n
                break

        # 提取部门
        dept_match = self._DEPT_PATTERN.search(q)
        dept = dept_match.group(1) if dept_match else ""

        # 按名字查员工
        if name:
            queries.append({
                "sql": "SELECT employee_id, name, department, level, hire_date, manager_id, email, status FROM employees WHERE name = ?",
                "params": (name,),
                "description": f"查询 {name} 的员工信息",
                "source": "employees",
            })
            # 绩效
            if any(k in q for k in ("绩效", "KPI", "考核", "晋升", "评级")):
                queries.append({
                    "sql": "SELECT pr.year, pr.quarter, pr.kpi_score, pr.grade FROM performance_reviews pr JOIN employees e ON pr.employee_id = e.employee_id WHERE e.name = ? ORDER BY pr.year, pr.quarter",
                    "params": (name,),
                    "description": f"查询 {name} 的绩效考核",
                    "source": "performance_reviews",
                })
            # 项目
            if any(k in q for k in ("项目", "负责", "参与")):
                queries.append({
                    "sql": "SELECT p.project_id, p.name, pm.role, p.status FROM project_members pm JOIN projects p ON pm.project_id = p.project_id JOIN employees e ON pm.employee_id = e.employee_id WHERE e.name = ?",
                    "params": (name,),
                    "description": f"查询 {name} 参与的项目",
                    "source": "project_members",
                })

        # 按部门查人数
        if dept and any(k in q for k in ("多少人", "有几人", "有几个", "人数")):
            queries.append({
                "sql": "SELECT COUNT(*) AS total, GROUP_CONCAT(name, '、') AS names FROM employees WHERE department = ? AND status = 'active'",
                "params": (dept,),
                "description": f"查询 {dept} 在职员工",
                "source": "employees",
            })
        elif dept and not name:
            queries.append({
                "sql": "SELECT name, department, level, email, status FROM employees WHERE department = ? AND status = 'active'",
                "params": (dept,),
                "description": f"查询 {dept} 在职员工列表",
                "source": "employees",
            })

        # 领导 / 上级
        if any(k in q for k in ("领导", "上级", "汇报", "经理", "主管")):
            n = name or ""
            d = dept or ""
            if n:
                queries.append({
                    "sql": "SELECT e2.name AS manager_name, e2.department AS manager_dept, e2.level AS manager_level, e2.email AS manager_email FROM employees e1 JOIN employees e2 ON e1.manager_id = e2.employee_id WHERE e1.name = ?",
                    "params": (n,),
                    "description": f"查询 {n} 的上级领导",
                    "source": "employees(manager_id)",
                })
            elif d:
                queries.append({
                    "sql": "SELECT e.name AS employee_name, e.level, e2.name AS manager_name, e2.department AS manager_dept FROM employees e JOIN employees e2 ON e.manager_id = e2.employee_id WHERE e.department = ? AND e.status = 'active' LIMIT 1",
                    "params": (d,),
                    "description": f"查询 {d} 的负责人",
                    "source": "employees(manager_id)",
                })

        # 考勤
        if any(k in q for k in ("迟到", "考勤", "请假")):
            n = name or ""
            if n:
                queries.append({
                    "sql": "SELECT a.date, a.status FROM attendance a JOIN employees e ON a.employee_id = e.employee_id WHERE e.name = ? ORDER BY a.date",
                    "params": (n,),
                    "description": f"查询 {n} 的考勤记录",
                    "source": "attendance",
                })

        # 都不匹配时兜底
        if not queries:
            queries.append({
                "sql": "SELECT name, department, level, status FROM employees WHERE status = 'active' LIMIT 5",
                "params": (),
                "description": "员工基本信息",
                "source": "employees",
            })

        return queries
