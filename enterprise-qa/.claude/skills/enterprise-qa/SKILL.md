---
name: enterprise-qa
description: 企业智能问答。处理员工信息、公司制度、项目数据、考勤绩效、晋升评定等企业内部查询。触发词：/qa, @enterprise, /enterprise-qa
metadata:
  short-description: 企业问答，查数据库和知识库

---

# Enterprise QA

用户提到员工/部门/考勤/绩效/晋升/制度/项目/报销/会议等内部话题时，按以下流程处理。

## 第一步：判断问题类型

| 类型 | 判断标准 | 示例 |
|------|---------|------|
| db_only | 问具体数据（邮箱、部门、人数、考勤次数） | "张三的邮箱？" |
| kb_only | 问制度规则（年假怎么算、迟到扣多少） | "年假怎么算？" |
| hybrid | 需要 DB 记录 + KB 规则综合判断 | "王五符合晋升条件吗？" |
| fuzzy | 宽泛没有明确查询目标 | "最近有什么事？" |

## 第二步：查询数据

### 数据库（SQLite 文件：`data/enterprise.db`）

表结构：
- **employees**(employee_id, name, department, level, hire_date, manager_id, email, status) — 10 人
- **projects**(project_id, name, lead_id, status, start_date, end_date, budget) — 5 个项目
- **project_members**(project_id, employee_id, role, join_date) — role: lead/core/contributor
- **attendance**(id, employee_id, date, status) — status: on_time/late/absent/on_leave，仅 2026-02 数据
- **performance_reviews**(id, employee_id, year, quarter, kpi_score, grade) — 仅 2025 年数据

当前日期：2026-03-27。查询方法：
```bash
sqlite3 data/enterprise.db "SELECT ..."
```
**必须用参数化查询（? 占位符），只执行 SELECT。**

### 知识库（`data/knowledge/` 目录）

| 文件 | 关键内容 |
|------|---------|
| hr_policies.md | 迟到扣款规则、年假(满1年5天+1/年上限15)、加班调休 |
| promotion_rules.md | P5→P6(满1年+2季KPI≥85+项目≥3)，P6→P7(满2年+4季KPI≥90+项目≥2) |
| tech_docs.md | Python/Go/React 技术栈、开发流程 |
| finance_rules.md | 报销标准(住宿≤500/天、餐饮≤200/天) |
| faq.md | 常见问题 |
| meeting_notes/ | 全员大会、技术同步会纪要 |

```bash
cat data/knowledge/<文件名>
```

### 一键查询（推荐，引擎自动处理全流程）

```bash
uv run python cli.py "问题"
```

引擎内部：意图分类 → LLM生成SQL → 参数化查询 → BM25+向量检索 → RRF融合 → LLM生成回答 → 来源标注

## 第三步：组织回答

1. 自然语言，不 dump 原始 SQL 或 JSON 数据
2. 标注来源：`employees 表` 或 `hr_policies.md §请假类型`
3. 信息不足时："没有找到相关信息"
4. 混合查询用表格对比晋升条件 vs 实际情况

## 测试验证

```bash
cd enterprise-qa
uv sync --extra dev
uv run pytest -v
```

## 安全

1. 只用 SELECT，不修改数据库
2. 参数化查询（? 占位符），禁止字符串拼接
3. 不编造数据
