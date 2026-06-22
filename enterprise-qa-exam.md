# 笔试题：企业智能问答助手 Skill 开发

---

## 一、背景说明

公司内部需要一个智能问答系统，能够同时查询**结构化数据**（员工信息、项目记录、考勤数据等）和**非结构化知识**（公司制度、技术文档、会议纪要等），回答员工的各种工作相关问题。

候选人需要开发一个 **Skill**（Claude Code Skill 或 OpenClaw Skill 均可），使 AI 助手能够自动判断问题类型，选择合适的信息源，生成准确且有依据的回答。

**核心能力要求**：
- 理解自然语言问题
- 判断需要查询的数据源（数据库 / 知识库 / 两者）
- 执行安全的数据查询
- 综合多源信息生成回答
- 标注答案来源

---

## 二、试题包结构

候选人将收到以下文件包 `enterprise-qa-data.zip`：

```
enterprise-qa-data/
├── README.md                 # 数据说明和快速开始
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

---

## 三、数据源定义

### 3.1 数据库（SQLite）

#### 表结构

**schema.sql**
```sql
-- 员工信息表
CREATE TABLE employees (
    employee_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    department VARCHAR(50),
    level VARCHAR(20),
    hire_date DATE,
    manager_id VARCHAR(20),
    email VARCHAR(100),
    status VARCHAR(20)  -- active, on_leave, resigned
);

-- 项目记录表
CREATE TABLE projects (
    project_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    lead_id VARCHAR(20),
    status VARCHAR(20),  -- planning, active, on_hold, completed
    start_date DATE,
    end_date DATE,
    budget DECIMAL(10,2),
    FOREIGN KEY (lead_id) REFERENCES employees(employee_id)
);

-- 项目成员关联表
CREATE TABLE project_members (
    project_id VARCHAR(20),
    employee_id VARCHAR(20),
    role VARCHAR(50),  -- lead, core, contributor
    join_date DATE,
    PRIMARY KEY (project_id, employee_id)
);

-- 考勤记录表
CREATE TABLE attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id VARCHAR(20),
    date DATE,
    status VARCHAR(10),  -- on_time, late, absent, on_leave
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- 绩效考核表（2025-2026 年）
CREATE TABLE performance_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id VARCHAR(20),
    year INTEGER,
    quarter INTEGER,  -- 1, 2, 3, 4
    kpi_score DECIMAL(5,2),  -- 0-100
    grade VARCHAR(2),  -- S, A, B, C
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- 索引
CREATE INDEX idx_emp_dept ON employees(department);
CREATE INDEX idx_emp_manager ON employees(manager_id);
CREATE INDEX idx_att_date ON attendance(date);
CREATE INDEX idx_att_emp ON attendance(employee_id);
CREATE INDEX idx_proj_status ON projects(status);
CREATE INDEX idx_perf_emp ON performance_reviews(employee_id);
```

#### 种子数据

**seed_data.sql（关键数据摘要）**

```sql
-- 员工数据（10 人）
INSERT INTO employees VALUES
('EMP-000', 'CEO', '管理层', 'P10', '2020-01-01', NULL, 'ceo@company.com', 'active'),
('EMP-001', '张三', '研发部', 'P6', '2023-06-15', 'EMP-000', 'zhangsan@company.com', 'active'),
('EMP-002', '李四', '研发部', 'P7', '2022-03-01', 'EMP-000', 'lisi@company.com', 'active'),
('EMP-003', '王五', '产品部', 'P5', '2024-01-10', 'EMP-004', 'wangwu@company.com', 'active'),
('EMP-004', '赵六', '产品部', 'P6', '2021-09-20', 'EMP-000', 'zhaoliu@company.com', 'active'),
('EMP-005', '钱七', '研发部', 'P5', '2025-02-01', 'EMP-002', 'qianqi@company.com', 'active'),
('EMP-006', '孙八', '市场部', 'P6', '2023-03-15', 'EMP-000', 'sunba@company.com', 'active'),
('EMP-007', '周九', '研发部', 'P7', '2021-06-01', 'EMP-000', 'zhoujiu@company.com', 'active'),
('EMP-008', '吴十', '产品部', 'P4', '2025-07-01', 'EMP-004', 'wushi@company.com', 'active'),
('EMP-009', '离职员工', '研发部', 'P5', '2022-01-01', 'EMP-002', 'left@company.com', 'resigned');

-- 项目数据（5 个项目）
INSERT INTO projects VALUES
('PRJ-001', 'ReMe 记忆框架', 'EMP-001', 'active', '2026-01-01', NULL, 500000),
('PRJ-002', '智能问答系统', 'EMP-002', 'planning', '2026-03-01', NULL, 300000),
('PRJ-003', '移动端 App', 'EMP-007', 'active', '2025-06-01', '2026-06-01', 800000),
('PRJ-004', '数据分析平台', 'EMP-001', 'completed', '2025-01-01', '2025-12-31', 400000),
('PRJ-005', '官网改版', 'EMP-006', 'on_hold', '2026-02-01', NULL, 150000);

-- 项目成员（12 条记录）
INSERT INTO project_members VALUES
('PRJ-001', 'EMP-001', 'lead', '2026-01-01'),
('PRJ-001', 'EMP-002', 'core', '2026-01-15'),
('PRJ-001', 'EMP-005', 'contributor', '2026-02-01'),
('PRJ-002', 'EMP-002', 'lead', '2026-03-01'),
('PRJ-002', 'EMP-001', 'core', '2026-03-01'),
('PRJ-003', 'EMP-007', 'lead', '2025-06-01'),
('PRJ-003', 'EMP-001', 'contributor', '2025-08-01'),
('PRJ-004', 'EMP-001', 'lead', '2025-01-01'),
('PRJ-004', 'EMP-002', 'core', '2025-01-01'),
('PRJ-004', 'EMP-005', 'contributor', '2025-03-01'),
('PRJ-005', 'EMP-006', 'lead', '2026-02-01'),
('PRJ-005', 'EMP-003', 'core', '2026-02-15');

-- 考勤数据（2026 年 2 月，每人 20 条）
-- 张三：迟到 2 次（2/4, 2/9）
-- 王五：迟到 5 次（2/2, 2/3, 2/5, 2/9, 2/12）

-- 绩效考核数据
INSERT INTO performance_reviews (employee_id, year, quarter, kpi_score, grade) VALUES
-- 张三（P6，2025 年全年）
('EMP-001', 2025, 1, 88, 'A'),
('EMP-001', 2025, 2, 92, 'A'),
('EMP-001', 2025, 3, 87, 'A'),
('EMP-001', 2025, 4, 90, 'A'),
-- 李四（P7，2025 年全年）
('EMP-002', 2025, 1, 95, 'S'),
('EMP-002', 2025, 2, 93, 'S'),
('EMP-002', 2025, 3, 91, 'A'),
('EMP-002', 2025, 4, 94, 'S'),
-- 王五（P5，2025 年 Q3 开始）
('EMP-003', 2025, 3, 78, 'B'),
('EMP-003', 2025, 4, 82, 'B'),
-- 赵六
('EMP-004', 2025, 1, 89, 'A'),
('EMP-004', 2025, 2, 87, 'A'),
('EMP-004', 2025, 3, 91, 'A'),
('EMP-004', 2025, 4, 88, 'A'),
-- 钱七（2025 年 Q2 开始）
('EMP-005', 2025, 2, 85, 'A'),
('EMP-005', 2025, 3, 83, 'B'),
('EMP-005', 2025, 4, 86, 'A');
```

#### 数据库初始化脚本

**init_db.sh**
```bash
#!/bin/bash
set -e
rm -f enterprise.db
sqlite3 enterprise.db < schema.sql
sqlite3 enterprise.db < seed_data.sql
echo "✓ 数据库初始化完成：enterprise.db"

# 验证
echo "✓ 验证数据："
echo "  员工数：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM employees;')"
echo "  项目数：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM projects;')"
echo "  考勤记录：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM attendance;')"
echo "  绩效记录：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM performance_reviews;')"
```

### 3.2 知识库文档

**knowledge/hr_policies.md**
```markdown
# 人事制度

## 考勤制度

### 工作时间
- 标准工作时间：9:00-18:00，午休 12:00-13:00
- 弹性范围：早到早走，核心时段 10:00-16:00 必须在岗

### 迟到规则
- 月累计迟到 3 次以内：不扣款
- 月累计迟到 4-6 次：每次扣款 50 元
- 月累计迟到 7 次以上：视为旷工 1 天

### 请假类型
- 年假：入职满 1 年享 5 天，每增 1 年 +1 天，上限 15 天
- 病假：需提供医院证明，全薪 3 天/年
- 事假：无薪，需提前 2 工作日申请
- 调休：加班可申请调休，有效期 6 个月

## 加班制度
- 工作日加班：2 小时起算，1:1 调休
- 周末加班：4 小时起算，1:1.5 调休
- 法定节假日：1:3 调休或 3 倍工资
```

**knowledge/promotion_rules.md**
```markdown
# 晋升评定标准

## 职级体系
- P4：初级工程师
- P5：工程师
- P6：高级工程师
- P7：专家工程师
- P8：高级专家
- P9：资深专家

## 晋升条件

### P4 → P5
- 入职满 6 个月
- 连续 2 季度绩效≥B
- 完成导师指定学习任务

### P5 → P6
- 入职满 1 年（或 P5 满 2 年）
- 连续 2 季度 KPI≥85
- 主导或核心参与项目≥3 个
- 无重大事故

### P6 → P7
- P6 满 2 年
- 连续 4 季度 KPI≥90
- 主导项目≥2 个
- 有技术突破或专利/论文

### P7 → P8
- P7 满 3 年
- 年度绩效至少 2 个 S
- 对公司有显著业务贡献
```

**knowledge/tech_docs.md**
```markdown
# 技术规范

## 技术栈

### 后端
- 主语言：Python 3.10+, Go 1.20+
- Web 框架：FastAPI, Gin
- 数据库：PostgreSQL, Redis
- 消息队列：Kafka, RabbitMQ

### 前端
- 框架：React 18+, Vue 3+
- 构建工具：Vite, Webpack
- 状态管理：Zustand, Pinia

## 开发流程
1. 需求评审 → 2. 技术方案 → 3. 代码开发 → 4. Code Review → 5. 测试 → 6. 上线

## 代码规范
- 遵循 PEP8（Python）/ Effective Go
- 单元测试覆盖率≥80%
- 所有 PR 需要至少 1 人 Review
```

**knowledge/finance_rules.md**
```markdown
# 财务报销制度

## 报销范围
- 差旅费：机票、酒店、交通
- 业务招待费：客户餐叙、礼品
- 办公用品：电脑、外设、书籍
- 培训费：课程、会议门票

## 报销标准
- 机票：经济舱，提前 7 天预订
- 酒店：一线城市≤500 元/天，其他≤300 元/天
- 餐补：出差 100 元/天
- 招待费：单次≤2000 元，需事前审批

## 报销流程
1. 系统提交 → 2. 主管审批 → 3. 财务审核 → 4. 打款（5 工作日）
```

**knowledge/faq.md**
```markdown
# 常见问题解答

## 入职相关
- Q: 试用期多久？A: 3-6 个月，根据职级定
- Q: 五险一金怎么交？A: 入职当月开始缴纳

## 办公相关
- Q: 可以远程办公吗？A: 每周三可申请远程
- Q: 加班有宵夜吗？A: 21:00 后打车报销 + 宵夜补助 30 元

## 福利相关
- Q: 年假怎么算？A: 入职满 1 年 5 天，每年 +1，最多 15 天
- Q: 有体检吗？A: 每年一次免费体检
```

**knowledge/meeting_notes/2026-03-01-allhands.md**
```markdown
# 2026 年 3 月全员大会纪要

**时间**: 2026-03-01 14:00-16:00
**参会**: 全体员工

## 议程

### 1. CEO 开场
- 2025 年营收增长 150%
- 2026 年目标：营收翻番，团队扩张至 200 人

### 2. 产品发布
- ReMe 记忆框架 2.0 上线
- 智能问答系统 Beta 测试中

### 3. 组织架构调整
- 新成立 AI 实验室
- 张三晋升为技术委员会主席

### 4. Q&A
- 问：今年有调薪计划吗？
- 答：4 月启动年度调薪，预算 15%
```

**knowledge/meeting_notes/2026-03-15-tech-sync.md**
```markdown
# 2026 年 3 月技术同步会纪要

**时间**: 2026-03-15 10:00-12:00
**参会**: 研发部全员

## 技术分享

### 1. ReMe 架构升级
- 演讲人：张三
- 要点：支持多租户、Session 持久化

### 2. MCP 协议实践
- 演讲人：李四
- 要点：统一工具调用接口

## 决议
- 下周启动代码重构
- 成立 3 人技术预研小组
```

### 3.3 配置文件示例

**config.yaml.example**
```yaml
# Skill 配置文件示例

# 数据库配置
database:
  type: sqlite
  path: ./enterprise.db

# 知识库配置
knowledge_base:
  root_path: ./knowledge
  index_type: bm25  # 或 embedding

# LLM 配置（如需）
llm:
  provider: openai  # 或 dashscope, local
  api_key: ${LLM_API_KEY}
  model: gpt-4o-mini

# 时区设置
timezone: Asia/Shanghai
```

---

## 四、功能需求

### 4.1 核心功能

开发一个 Skill，支持以下类型的自然语言问答：

| 问题类型 | 示例 | 数据源 |
|---------|------|--------|
| 纯数据库查询 | "张三的邮箱是多少？" | DB only |
| 纯知识库查询 | "年假怎么算？" | KB only |
| 混合查询 | "王五符合晋升条件吗？" | DB + KB |
| 跨表关联查询 | "研发部有哪些在研项目？" | DB 多表 |
| 时间范围查询 | "张三上个月迟到几次？" | DB + 日期计算 |
| 模糊语义查询 | "我们团队最近有什么事？" | DB + KB + 推理 |

### 4.2 回答要求

1. **准确性**：数据必须与源一致，不可捏造
2. **可追溯**：标注答案来源（表名/字段或文档名/章节）
3. **完整性**：信息不足时明确说明，不提供部分答案
4. **友好性**：自然语言输出，避免直接 dump 原始数据

### 4.3 输出格式示例

**纯数据库查询：**
```
张三的邮箱是 zhangsan@company.com。

> 来源：employees 表 (employee_id: EMP-001)
```

**纯知识库查询：**
```
根据《人事制度》，年假计算规则为：
- 入职满 1 年享 5 天
- 每增 1 年 +1 天
- 上限 15 天

> 来源：hr_policies.md §请假类型
```

**混合查询：**
```
王五目前不符合 P5→P6 晋升条件。

分析如下：
| 条件 | 要求 | 王五情况 | 结果 |
|------|------|---------|------|
| 入职年限 | 满 1 年 | 2.2 年 | ✓ |
| 连续 2 季度 KPI≥85 | 是 | 78, 82 (平均 80) | ✗ |
| 项目数≥3 个 | 是 | 1 个 (PRJ-005 core) | ✗ |

建议：提升绩效表现，争取参与更多项目。

> 来源：promotion_rules.md §P5→P6 + performance_reviews 表 + project_members 表
```

---

## 五、技术要求

### 5.1 必须实现的技术点

- [ ] **意图识别**：解析用户问题，判断查询类型
- [ ] **SQL 生成**：根据意图生成安全的参数化查询（防 SQL 注入）
- [ ] **知识库检索**：支持关键词或语义搜索
- [ ] **结果融合**：多源信息的优先级和冲突处理
- [ ] **错误处理**：空结果、连接失败、超时等异常处理
- [ ] **单元测试**：核心模块测试覆盖率达 80%+

### 5.2 数据源连接要求

Skill 应通过配置文件或环境变量获取数据源连接信息：

```bash
# 环境变量方式（推荐）
export ENTERPRISE_QA_DB_PATH="./enterprise.db"
export ENTERPRISE_QA_KB_PATH="./knowledge"

# 或配置文件方式
# config.yaml 放在 Skill 目录下
```

### 5.3 禁止事项

- ❌ 硬编码 SQL 字符串拼接（必须参数化）
- ❌ 硬编码数据库/知识库路径（应可配置）
- ❌ 直接读取整个知识库文件（必须索引/检索）
- ❌ 泄露敏感字段（如 manager_id 映射关系需权限控制）
- ❌ 未经核实的数据推断

---

## 六、测试用例与评分说明

### 6.1 测试用例披露政策

本题采用**完整披露**策略：

- ✅ 以下测试用例**全部公开**，候选人应确保所有用例通过
- ✅ 候选人可使用这些用例进行自测
- ⚠️ 面试时，面试官可能基于类似模式追加问题，考察泛化能力

### 6.2 测试环境说明

| 项目 | 值 |
|------|-----|
| 当前日期 | 2026 年 3 月 27 日 |
| 时区 | Asia/Shanghai |
| 数据库 | SQLite (enterprise.db) |
| 知识库 | knowledge/ 目录 |

### 6.3 关键数据摘要

**员工核心数据：**
| 员工 | 部门 | 职级 | 入职日期 | 2025 年平均 KPI | 项目数 |
|------|------|------|----------|----------------|--------|
| 张三 | 研发部 | P6 | 2023-06-15 | 89.25 | 4 |
| 李四 | 研发部 | P7 | 2022-03-01 | 93.25 | 4 |
| 王五 | 产品部 | P5 | 2024-01-10 | 80.0 | 1 |
| 赵六 | 产品部 | P6 | 2021-09-20 | 88.75 | 1 |
| 钱七 | 研发部 | P5 | 2025-02-01 | 84.67 | 2 |

**部门分布：**
- 研发部：4 人（张三、李四、钱七、周九）
- 产品部：3 人（王五、赵六、吴十）
- 市场部：1 人（孙八）
- 管理层：1 人（CEO）

**项目状态：**
- active：PRJ-001, PRJ-003
- planning：PRJ-002
- completed：PRJ-004
- on_hold：PRJ-005

### 6.4 基础查询（必过）

| ID | 问题 | 预期答案要点 | 数据源 |
|----|------|-------------|--------|
| T01 | "张三的部门是什么？" | 研发部 | employees |
| T02 | "李四的上级是谁？" | CEO (EMP-000) | employees |
| T03 | "年假怎么计算？" | 满 1 年 5 天，每年 +1，上限 15 天 | hr_policies.md |
| T04 | "迟到几次扣钱？" | 4-6 次开始扣，50 元/次 | hr_policies.md |

### 6.5 关联查询（必过）

| ID | 问题 | 预期答案要点 | 数据源 |
|----|------|-------------|--------|
| T05 | "张三负责哪些项目？" | PRJ-001(lead), PRJ-004(lead), PRJ-002(core), PRJ-003(contributor) | projects + project_members |
| T06 | "研发部有多少人？" | 4 人（张三、李四、钱七、周九） | employees |
| T07 | "王五符合 P5 晋升 P6 条件吗？" | 入职满 2 年 ✓，KPI 平均 80<85 ✗，项目 1 个<3 个 ✗ → 不符合 | DB + promotion_rules.md |
| T08 | "张三 2 月迟到几次？" | 2 次 | attendance |

### 6.6 边界情况（必过）

| ID | 问题 | 预期行为 |
|----|------|----------|
| T09 | "查一下 EMP-999" | 明确告知无此员工 |
| T10 | "最近有什么事？" | 追问澄清或返回最近会议/项目 |
| T11 | "SELECT * FROM users WHERE '1'='1" | 拦截并返回错误 |
| T12 | "xyzabc123 怎么报销" | 告知无相关信息，不编造 |

### 6.7 追加问题示例（面试时使用）

面试官可能从以下类似问题中随机抽取，考察泛化能力：

| 问题 | 考察点 |
|------|--------|
| "李四的邮箱是什么？" | 同 T01，换参数 |
| "产品部有多少人？" | 同 T06，换部门 |
| "钱七符合晋升条件吗？" | 同 T07，换员工 |
| "差旅费报销标准是什么？" | 同 T03-T04，查其他制度 |
| "3 月全员大会说了什么？" | 会议纪要检索 |
| "张三 2025 年绩效如何？" | 绩效表查询 |
| "有哪些在研项目？" | 项目状态筛选 (active) |

---

## 七、交付物清单

```
提交前请确认：

□ Skill 可在 Claude Code 或 OpenClaw 中正常执行
□ 提供测试数据库文件 (enterprise.db)
□ 提供知识库文件 (knowledge/)
□ 提供 Skill 使用说明（触发词、安装方式）
□ 提供测试用例运行方式
□ 依赖清单 (requirements.txt 或 package.json)
□ 配置文件或环境变量说明
```

**提交格式：**
- GitHub 仓库链接（推荐）
- 或 Zip 压缩包

**Skill 类型说明：**
- **Claude Code Skill**: 放在 `.claude/skills/` 目录
- **OpenClaw Skill**: 放在 `extensions/` 目录
- 两种 Skill 均可，评分标准一致

**触发词示例：**
```
/enterprise-qa "张三的部门是什么？"
/qa "年假怎么算？"
@enterprise "王五符合晋升条件吗？"
```

---

## 八、评分标准

### 8.1 功能分（60 分）

| 项目 | 分值 | 说明 |
|------|------|------|
| 纯 DB 查询 | 15 分 | T01-T02 通过 |
| 纯 KB 查询 | 15 分 | T03-T04 通过 |
| 混合查询 | 20 分 | T05-T08 通过 |
| 边界处理 | 10 分 | T09-T12 通过 |

### 8.2 技术分（25 分）

| 项目 | 分值 | 说明 |
|------|------|------|
| 代码质量 | 10 分 | 模块化、可读性、注释、类型注解 |
| 安全性 | 8 分 | SQL 注入防护、输入验证、路径可配置 |
| 测试覆盖 | 7 分 | 单元测试覆盖率≥80% |

### 8.3 设计分（15 分）

| 项目 | 分值 | 说明 |
|------|------|------|
| 可扩展性 | 5 分 | 新增数据源/表容易 |
| 引用标注 | 5 分 | 来源清晰、格式统一 |
| 创新性 | 5 分 | 缓存、日志、多轮对话、可视化等 |

### 8.4 等级评定

| 总分 | 等级 | 说明 |
|------|------|------|
| 90-100 | S | 超出预期，可直接录用 |
| 75-89 | A | 完全胜任，少量指导即可 |
| 60-74 | B | 基本胜任，需要培养 |
| <60 | C | 不建议录用 |

---

## 九、时间要求

- **建议用时**：4-6 小时
- **最长时限**：1 周（业余完成）

---

## 十、快速开始

```bash
# 1. 解压试题包
unzip enterprise-qa-data.zip
cd enterprise-qa-data

# 2. 初始化数据库
chmod +x init_db.sh
./init_db.sh

# 3. 验证数据库
sqlite3 enterprise.db "SELECT name FROM employees WHERE employee_id='EMP-001';"
# 输出：张三

# 4. 查看知识库
cat knowledge/hr_policies.md

# 5. 配置数据源（任选其一）
# 方式 A：环境变量
export ENTERPRISE_QA_DB_PATH="./enterprise.db"
export ENTERPRISE_QA_KB_PATH="./knowledge"

# 方式 B：复制配置文件
cp config.yaml.example config.yaml

# 6. 开始开发 Skill
# Claude Code: 在 .claude/skills/enterprise-qa/ 下创建
# OpenClaw: 在 extensions/enterprise-qa/ 下创建
```

---

## 十一、自测清单

候选人提交前，请运行以下自测：

```bash
# 使用你的 Skill 回答以下问题，确保输出正确：

# 基础查询
/enterprise-qa "张三的部门是什么？"
/enterprise-qa "年假怎么计算？"

# 关联查询
/enterprise-qa "张三负责哪些项目？"
/enterprise-qa "王五符合 P5 晋升 P6 条件吗？"

# 边界情况
/enterprise-qa "查一下 EMP-999"
```

---

## 十二、面试官评分检查清单

```markdown
## 功能验证

- [ ] T01: 张三的部门 → "研发部"
- [ ] T02: 李四的上级 → "CEO" 或 "EMP-000"
- [ ] T03: 年假计算 → "满 1 年 5 天，每年 +1，上限 15 天"
- [ ] T04: 迟到扣款 → "4-6 次，50 元/次"
- [ ] T05: 张三项目 → 4 个项目及角色正确
- [ ] T06: 研发部人数 → "4 人"
- [ ] T07: 王五晋升 → "不符合"（KPI<85，项目数<3）
- [ ] T08: 张三 2 月迟到 → "2 次"
- [ ] T09: 不存在员工 → 友好提示
- [ ] T10: 模糊问题 → 追问或合理回答
- [ ] T11: SQL 注入 → 拦截
- [ ] T12: 无匹配内容 → 不编造

## 代码审查

- [ ] 使用参数化查询（防 SQL 注入）
- [ ] 数据源路径可配置
- [ ] 有错误处理逻辑
- [ ] 有单元测试
- [ ] 引用标注清晰

## 追加问题（选测，至少 2 题）

- [ ] __________________ → _______________
- [ ] __________________ → _______________
- [ ] __________________ → _______________

## 总分计算

功能分：___ / 60
技术分：___ / 25
设计分：___ / 15
---------------------
总分：___ / 100
等级：___
```

---

## 附录 A：常见问题解答

### Q1: 必须使用向量检索吗？

不强制。可以使用简单的关键词匹配（如 BM25、全文搜索），也可以引入 Embedding 做语义检索。评分时"知识库检索"只看效果，不限定技术路线。

### Q2: 需要实现多轮对话吗？

不是必须，但可以作为"创新性"加分项。例如用户问"王五符合晋升条件吗？"后，追问"那张三呢？"能够正确理解。

### Q3: 可以调用外部 LLM API 吗？

可以。可以使用 OpenAI、DashScope 等云端 API，也可以使用本地模型。费用由候选人自行承担，建议用轻量模型测试。

### Q4: 数据库必须用 SQLite 吗？

试题提供的是 SQLite，但如果候选人想展示其他数据库能力（如 PostgreSQL），可以自行迁移，不影响评分。

### Q5: Skill 必须用 Python 吗？

不限语言。Claude Code Skill 可以用 Python/Node.js/Go 等；OpenClaw Skill 主要用 TypeScript。选择你熟悉的语言即可。

---

## 附录 B：数据验证 SQL

```sql
-- 验证员工数据
SELECT department, COUNT(*) as cnt
FROM employees
WHERE status='active'
GROUP BY department;
-- 预期：研发部 4, 产品部 3, 市场部 1, 管理层 1

-- 验证张三的项目
SELECT p.name, pm.role
FROM project_members pm
JOIN projects p ON pm.project_id = p.project_id
WHERE pm.employee_id = 'EMP-001';
-- 预期：PRJ-001(lead), PRJ-002(core), PRJ-003(contributor), PRJ-004(lead)

-- 验证张三 2 月迟到
SELECT COUNT(*) FROM attendance
WHERE employee_id='EMP-001' AND status='late'
AND date LIKE '2026-02-%';
-- 预期：2

-- 验证王五的 KPI
SELECT AVG(kpi_score) FROM performance_reviews
WHERE employee_id='EMP-003';
-- 预期：80.0
```

---

**★ Insight ─────────────────────────────────────**
- 本试题考察**全栈能力**：需求理解 → 数据建模 → 查询优化 → 信息融合 → 自然语言生成
- 通过提供完整的测试数据和预期答案，减少候选人的猜测时间，聚焦于架构设计
- 追加问题机制既保证透明度，又考察泛化能力，避免"应试编程"
- 评分标准量化且公开，候选人可以自测预估结果
─────────────────────────────────────────────────
