# 技术规范

## 技术栈

### 后端技术

| 类别 | 技术选型 | 版本要求 |
|------|---------|---------|
| 主语言 | Python, Go | Python 3.10+, Go 1.20+ |
| Web 框架 | FastAPI, Gin | 最新稳定版 |
| 数据库 | PostgreSQL, Redis | PostgreSQL 14+, Redis 7+ |
| 消息队列 | Kafka, RabbitMQ | - |
| ORM | SQLAlchemy, GORM | - |
| 测试框架 | pytest, testing | - |

### 前端技术

| 类别 | 技术选型 | 版本要求 |
|------|---------|---------|
| 框架 | React, Vue | React 18+, Vue 3+ |
| 构建工具 | Vite, Webpack | Vite 4+ |
| 状态管理 | Zustand, Pinia | - |
| UI 组件库 | Ant Design, Element Plus | - |
| CSS 框架 | Tailwind CSS | 3.x |

### 基础设施

| 类别 | 技术选型 |
|------|---------|
| 容器化 | Docker, Kubernetes |
| CI/CD | GitHub Actions, ArgoCD |
| 监控 | Prometheus, Grafana |
| 日志 | ELK Stack |
| 云服务 | AWS, 阿里云 |

## 开发流程

### 标准流程

```
需求评审 → 技术方案 → 代码开发 → Code Review → 测试 → 上线
```

### 各阶段说明

| 阶段 | 输出物 | 参与人 |
|------|-------|--------|
| 需求评审 | PRD、原型 | PM、研发、测试 |
| 技术方案 | 设计文档 | 研发、架构师 |
| 代码开发 | 代码、单元测试 | 研发 |
| Code Review | CR 意见、修改 | 研发（至少 1 人 Review） |
| 测试 | 测试报告 | 测试、研发 |
| 上线 | 发布记录 | 运维、研发 |

## 代码规范

### Python

- 遵循 [PEP8](https://pep8.org/)
- 类型注解：推荐添加 type hints
- 文档字符串：公共 API 必须有 docstring
- 测试覆盖率：≥80%

### Go

- 遵循 [Effective Go](https://go.dev/doc/effective_go)
- 错误处理：必须检查 error
- 注释：公共导出必须有注释
- 测试覆盖率：≥80%

### 通用规范

- 命名：见名知意，英文命名
- 函数：单一职责，不超过 50 行
- 文件：不超过 500 行
- PR：原子提交，描述清晰

## Code Review 要求

- 所有 PR 需要至少 **1 人 Review** 后方可合并
- 核心代码（支付、权限、安全）需要 **2 人 Review**
- PR 描述必须包含：
  - 修改目的
  - 测试方式
  - 影响范围

## 技术债务

- 每个迭代预留 20% 时间处理技术债
- 技术债录入 backlog，定期清理
- 严重技术债（影响稳定性）优先处理

---

**版本**：v2026.1
**生效日期**：2026 年 1 月 1 日
**解释部门**：技术委员会
