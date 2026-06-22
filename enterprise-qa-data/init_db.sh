#!/bin/bash
# 企业智能问答助手 - 数据库初始化脚本
# enterprise-qa-data/init_db.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  企业智能问答助手 - 数据库初始化"
echo "=========================================="

# 删除旧数据库
rm -f enterprise.db
echo "✓ 清理旧数据库..."

# 创建新数据库
sqlite3 enterprise.db < schema.sql
echo "✓ 创建表结构..."

sqlite3 enterprise.db < seed_data.sql
echo "✓ 导入种子数据..."

# 验证数据
echo ""
echo "=========================================="
echo "  数据验证"
echo "=========================================="
echo "  员工数：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM employees;')"
echo "  项目数：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM projects;')"
echo "  项目成员数：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM project_members;')"
echo "  考勤记录：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM attendance;')"
echo "  绩效记录：$(sqlite3 enterprise.db 'SELECT COUNT(*) FROM performance_reviews;')"
echo ""

# 快速测试
echo "=========================================="
echo "  快速测试"
echo "=========================================="
echo "  张三的部门：$(sqlite3 enterprise.db "SELECT department FROM employees WHERE employee_id='EMP-001';")"
echo "  研发部人数：$(sqlite3 enterprise.db "SELECT COUNT(*) FROM employees WHERE department='研发部' AND status='active';")"
echo "  张三 2 月迟到：$(sqlite3 enterprise.db "SELECT COUNT(*) FROM attendance WHERE employee_id='EMP-001' AND status='late' AND date LIKE '2026-02-%';")"
echo ""

echo "✓ 数据库初始化完成：enterprise.db"
echo "=========================================="
