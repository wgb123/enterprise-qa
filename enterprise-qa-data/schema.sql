-- 企业智能问答助手 - 数据库表结构
-- enterprise-qa-data/schema.sql

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
