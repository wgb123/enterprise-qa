# 企业智能问答助手 - 试题数据包

本数据包包含笔试题"企业智能问答助手 Skill 开发"所需的全部测试数据。

## 文件结构

```
enterprise-qa-data/
├── README.md                 # 本文件
├── schema.sql                # 数据库表结构
├── seed_data.sql             # 测试种子数据
├── init_db.sh                # 数据库初始化脚本
├── config.yaml.example       # 配置文件示例
└── knowledge/
    ├── hr_policies.md        # 人事制度
    ├── promotion_rules.md    # 晋升标准
    ├── tech_docs.md          # 技术规范
    ├── finance_rules.md      # 财务制度
    ├── faq.md                # 常见问题
    └── meeting_notes/
        ├── 2026-03-01-allhands.md
        └── 2026-03-15-tech-sync.md
```

## 快速开始

### 1. 初始化数据库

```bash
chmod +x init_db.sh
./init_db.sh
```

### 2. 验证数据

```bash
sqlite3 enterprise.db "SELECT name FROM employees WHERE employee_id='EMP-001';"
# 输出：张三
```

### 3. 配置环境变量

```bash
export ENTERPRISE_QA_DB_PATH="./enterprise.db"
export ENTERPRISE_QA_KB_PATH="./knowledge"
```

## 数据摘要

### 员工分布

| 部门 | 人数 | 员工 ID |
|------|------|--------|
| 研发部 | 4 | EMP-001, EMP-002, EMP-005, EMP-007 |
| 产品部 | 3 | EMP-003, EMP-004, EMP-008 |
| 市场部 | 1 | EMP-006 |
| 管理层 | 1 | EMP-000 |

### 项目状态

| 状态 | 项目 | 负责人 |
|------|------|--------|
| active | PRJ-001, PRJ-003 | 张三、周九 |
| planning | PRJ-002 | 李四 |
| completed | PRJ-004 | 张三 |
| on_hold | PRJ-005 | 孙八 |

### 关键员工数据

| 员工 | 部门 | 职级 | 入职日期 | 2025 年平均 KPI | 项目数 |
|------|------|------|----------|----------------|--------|
| 张三 | 研发部 | P6 | 2023-06-15 | 89.25 | 4 |
| 李四 | 研发部 | P7 | 2022-03-01 | 93.25 | 4 |
| 王五 | 产品部 | P5 | 2024-01-10 | 80.0 | 1 |
| 赵六 | 产品部 | P6 | 2021-09-20 | 88.75 | 1 |
| 钱七 | 研发部 | P5 | 2025-02-01 | 84.67 | 2 |

## 测试用例快速验证

```bash
# T01: 张三的部门
sqlite3 enterprise.db "SELECT department FROM employees WHERE employee_id='EMP-001';"
# 预期：研发部

# T06: 研发部人数
sqlite3 enterprise.db "SELECT COUNT(*) FROM employees WHERE department='研发部' AND status='active';"
# 预期：4

# T08: 张三 2 月迟到
sqlite3 enterprise.db "SELECT COUNT(*) FROM attendance WHERE employee_id='EMP-001' AND status='late' AND date LIKE '2026-02-%';"
# 预期：2

# T07: 王五的 KPI
sqlite3 enterprise.db "SELECT AVG(kpi_score) FROM performance_reviews WHERE employee_id='EMP-003';"
# 预期：80.0
```

## 知识库文档说明

| 文档 | 用途 | 测试用例 |
|------|------|----------|
| hr_policies.md | 考勤、请假、加班制度 | T03, T04 |
| promotion_rules.md | 晋升评定标准 | T07 |
| tech_docs.md | 技术栈规范 | 追加问题 |
| finance_rules.md | 财务报销制度 | 追加问题 |
| faq.md | 常见问题 | 追加问题 |
| meeting_notes/ | 会议纪要 | 追加问题 |

## 注意事项

1. 数据库使用 SQLite，无需额外配置数据库服务
2. 所有日期均为 Asia/Shanghai 时区
3. 当前日期设定为 2026 年 3 月 27 日
4. 考勤数据仅包含 2026 年 2 月（完整 20 个工作日）
5. 绩效数据仅包含 2025 年（4 个季度）

## 问题反馈

如有数据问题，请联系出题人。
