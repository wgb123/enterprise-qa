# 企业智能问答助手

一个企业级智能问答系统，支持同时查询**结构化数据**（员工信息、项目数据、考勤、绩效等）和**非结构化知识**（公司制度、技术文档、会议纪要等）。

基于自然语言理解，自动判断问题类型，选择合适的检索方式，生成准确且有依据的回答。

---

## 目录

- [快速开始](#快速开始)
- [使用方式](#使用方式)
- [配置说明](#配置说明)
- [功能概述](#功能概述)
- [运行测试](#运行测试)
- [项目结构](#项目结构)
- [依赖清单](#依赖清单)
- [交付物清单](#交付物清单)

---

## 快速开始

### 环境要求

- Python >= 3.10
- SQLite 3.x（系统预装）
- uv（推荐）或 pip

### 1. 安装依赖

```bash
cd enterprise-qa

# 使用 uv（推荐）
uv sync

# 开发依赖（运行测试）
uv sync --extra dev
```

### 2. 初始化数据库

```bash
cd ../enterprise-qa-data
chmod +x init_db.sh
./init_db.sh
```

### 3. 配置

配置文件位于 `enterprise-qa/config.yaml`，参考 `enterprise-qa-data/config.yaml.example`：

```yaml
database:
  type: sqlite
  path: ../enterprise-qa-data/enterprise.db   # 数据库路径

knowledge_base:
  root_path: ../enterprise-qa-data/knowledge   # 知识库目录
  index_type: hybrid                           # bm25 / vector / hybrid

llm:
  provider: deepseek
  api_key: your_api_key_here
  api_base: https://api.deepseek.com/v1
  model: deepseek-v4-flash

embedding:
  mode: local                     # local / api
  local_model: BAAI/bge-small-zh-v1.5
  dimension: 512

timezone: Asia/Shanghai
```

> **注意：** 数据库路径和知识库路径均为相对路径（相对于 `enterprise-qa/` 目录）。
> LLM API Key 可设置环境变量 `ENTERPRISE_QA_LLM_API_KEY` 覆盖。

---

## 使用方式

### 方式一：Web 界面（推荐）

启动 HTTP 服务器：

```bash
cd enterprise-qa
uv run python server.py [端口号]
```

默认端口：**8080**。打开浏览器访问 `http://localhost:8080` 即可使用。

**界面特性：**
- 💬 三栏布局：左侧项目信息 | 中间聊天区域 | 右侧会话记录
- 🎯 SSE 流式输出，逐步展示思考过程
- 🧠 步骤追踪（意图识别 → SQL 生成 → 知识库检索 → LLM 格式化）
- 📎 答案来源标注
- 💾 会话历史持久化

### 方式二：命令行交互

```bash
cd enterprise-qa
uv run python cli.py
```

进入交互模式后输入问题，系统实时流式输出回答。输入 `/quit`、`/exit` 或 `/q` 退出。

### 方式三：单次查询

```bash
cd enterprise-qa
uv run python cli.py "张三的邮箱是多少？"
```

---

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ENTERPRISE_QA_DB_PATH` | 数据库路径 | config.yaml 中的 database.path |
| `ENTERPRISE_QA_KB_PATH` | 知识库目录 | config.yaml 中的 knowledge_base.root_path |
| `ENTERPRISE_QA_LLM_API_KEY` | LLM API Key | config.yaml 中的 llm.api_key |

### 检索模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `bm25` | 仅 BM25 关键词检索 | 轻量快速，不依赖向量模型 |
| `vector` | 仅向量语义检索 | 需要语义匹配 |
| `hybrid` | BM25 + 向量混合（RRF 融合） | 综合效果最好（默认） |

---

## 功能概述

### 支持的问题类型

| 类型 | 示例 | 数据源 |
|------|------|--------|
| 纯数据库查询 | "张三的邮箱是多少？" | DB only |
| 纯知识库查询 | "年假怎么算？" | KB only |
| 混合查询 | "王五符合晋升条件吗？" | DB + KB |
| 跨表关联查询 | "研发部有哪些在研项目？" | DB 多表 |
| 时间范围查询 | "张三上个月迟到几次？" | DB + 日期计算 |
| 模糊语义查询 | "我们团队最近有什么事？" | DB + KB + 推理 |

### 回答要求

- ✅ **准确性**：数据与源一致，不捏造
- ✅ **可追溯**：标注答案来源（表名/字段或文档名/章节）
- ✅ **完整性**：信息不足时明确说明
- ✅ **友好性**：自然语言输出，不 dump 原始数据

---

## 运行测试

```bash
cd enterprise-qa

# 运行全部测试
uv run python -m pytest tests/ -v

# 运行带覆盖率报告
uv run python -m pytest tests/ -v --cov=src --cov-report=term-missing

# 运行特定测试文件
uv run python -m pytest tests/test_intent_classifier.py -v

# 运行特定测试类
uv run python -m pytest tests/test_response_fusion.py::TestResponseFusion -v
```

### 测试覆盖模块

| 模块 | 说明 | 覆盖内容 |
|------|------|----------|
| `test_config.py` | 配置加载测试 | 默认配置、环境变量覆盖、YAML 覆盖、索引类型、嵌入配置 |
| `test_intent_classifier.py` | 意图分类测试 | 降级兜底、LLM 解析（db/kb/hybrid）、实体提取 |
| `test_kb_retriever.py` | 知识库检索测试 | 文档加载、中文分词、BM25 搜索、混合检索 |
| `test_response_fusion.py` | 结果融合测试 | 各类查询、空结果、流式输出一致性 |
| `test_sql_generator.py` | SQL 生成测试 | Schema 构建、降级 SQL、只读校验 |

---

## 项目结构

```
enterprise-qa/
├── cli.py                          # 命令行入口
├── server.py                       # HTTP 服务器（SSE 流式）
├── config.yaml                     # 配置文件
├── pyproject.toml                  # 项目配置与依赖
├── static/
│   └── index.html                  # Web 前端界面
├── data/
│   └── conversations.json          # 会话持久化文件（自动生成）
├── src/
│   └── enterprise_qa/
│       ├── __init__.py
│       ├── config.py               # 配置加载
│       ├── conversation.py         # 会话管理
│       ├── db_connector.py         # 数据库连接器
│       ├── intent_classifier.py    # 意图分类器
│       ├── kb_retriever.py         # 知识库检索器
│       ├── response_fusion.py      # 结果融合与流式输出
│       └── sql_generator.py        # SQL 生成器
├── tests/
│   ├── test_config.py
│   ├── test_intent_classifier.py
│   ├── test_kb_retriever.py
│   ├── test_response_fusion.py
│   └── test_sql_generator.py
└── README.md                       # 本文件

enterprise-qa-data/                 # 数据包（外部依赖）
├── enterprise.db                   # SQLite 数据库
├── schema.sql                      # 数据库表结构
├── seed_data.sql                   # 种子数据
├── init_db.sh                      # 数据库初始化脚本
├── config.yaml.example             # 配置文件示例
└── knowledge/                      # 知识库文档
    ├── hr_policies.md              # 人事制度
    ├── promotion_rules.md          # 晋升标准
    ├── tech_docs.md                # 技术规范
    ├── finance_rules.md            # 财务制度
    ├── faq.md                      # 常见问题
    └── meeting_notes/
        ├── 2026-03-01-allhands.md  # 全员大会纪要
        └── 2026-03-15-tech-sync.md # 技术同步会纪要
```

---

## 依赖清单

项目核心依赖（详见 `pyproject.toml`）：

| 包名 | 用途 |
|------|------|
| `pyyaml` | 配置文件解析 |
| `pydantic` | 配置数据模型 |
| `rank-bm25` | BM25 关键词检索 |
| `numpy` | 向量计算 |
| `requests` | LLM API 调用 |
| `qdrant-client` | 向量存储与检索 |
| `torch` | 嵌入模型推理 |
| `transformers` | BGE 嵌入模型 |
| `scipy` | RRF 融合计算 |

开发依赖：`pytest`、`pytest-cov`

---

## 交付物清单

- [x] 项目可在 Python 3.10+ 环境中正常执行
- [x] 提供测试数据库文件 `enterprise-qa-data/enterprise.db`
- [x] 提供知识库文件 `enterprise-qa-data/knowledge/`
- [x] 提供使用说明（本文件 / 安装方式、配置、运行）
- [x] 提供测试用例运行方式（`pytest tests/ -v`）
- [x] 依赖清单（`pyproject.toml` + 本文件）
- [x] 配置文件说明（`config.yaml` + 环境变量）
