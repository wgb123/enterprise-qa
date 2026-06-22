# SQL Query Rules

## Schema

```sql
-- 员工表
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

-- 项目表
CREATE TABLE projects (
    project_id VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    lead_id VARCHAR(20),
    status VARCHAR(20),  -- planning, active, on_hold, completed
    start_date DATE, end_date DATE,
    budget DECIMAL(10,2),
    FOREIGN KEY (lead_id) REFERENCES employees(employee_id)
);

-- 项目成员
CREATE TABLE project_members (
    project_id VARCHAR(20), employee_id VARCHAR(20),
    role VARCHAR(50),  -- lead, core, contributor
    join_date DATE,
    PRIMARY KEY (project_id, employee_id)
);

-- 考勤
CREATE TABLE attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id VARCHAR(20), date DATE,
    status VARCHAR(10),  -- on_time, late, absent, on_leave
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- 绩效
CREATE TABLE performance_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id VARCHAR(20), year INTEGER, quarter INTEGER,
    kpi_score DECIMAL(5,2), grade VARCHAR(2),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);
```

## Business Rules

1. 查人数 = 只统计在职（status='active'），离职员工不算
2. 查某人负责/参与的项目 = projects.lead_id + project_members 两个表都查，用 UNION
3. 查制度/规则 = 不需要 SQL，查知识库

## Join Patterns

**某人负责的项目**（核心模式）
```sql
-- 作为负责人
SELECT p.project_id, p.name, 'lead' AS role
FROM projects p
JOIN employees e ON p.lead_id = e.employee_id
WHERE e.name = ?
UNION
-- 作为成员
SELECT p.project_id, p.name, pm.role
FROM project_members pm
JOIN projects p ON pm.project_id = p.project_id
JOIN employees e ON pm.employee_id = e.employee_id
WHERE e.name = ?
```

**某人考勤迟到次数**
```sql
SELECT COUNT(*) as late_count
FROM attendance a
JOIN employees e ON a.employee_id = e.employee_id
WHERE e.name = ? AND a.status = 'late'
```

**某部门在职员工（必须返回人数 + 姓名列表，缺一不可）**
```sql
-- 必须同时返回 total 和 names 两个字段
SELECT COUNT(*) AS total, GROUP_CONCAT(name, '、') AS names
FROM employees
WHERE department = ? AND status = 'active'
```

## Safety Rules

1. 只生成 SELECT 查询
2. 必须用 ? 占位符参数化，禁止拼接
3. 姓名、日期等用户输入都走 params，不拼 SQL
4. 多条查询才能完整回答时生成多个
