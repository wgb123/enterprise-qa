"""数据库连接与操作"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from enterprise_qa.config import Config


class DatabaseError(Exception):
    """数据库操作异常"""


class DBConnector:
    """SQLite 数据库连接器"""

    def __init__(self, config: Config):
        db_path = Path(config.database.path)
        if not db_path.exists():
            raise DatabaseError(f"数据库文件不存在: {db_path}")
        self.db_path = str(db_path.resolve())

    @contextmanager
    def connect(self):
        """获取数据库连接（上下文管理器，自动提交/回滚）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """执行参数化查询，返回字典列表"""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return results

    def execute_many(self, sql: str, params_list: list[tuple]) -> int:
        """批量执行"""
        with self.connect() as conn:
            cursor = conn.executemany(sql, params_list)
            return cursor.rowcount

    def get_table_schema(self) -> list[dict[str, str]]:
        """获取所有表的 schema 信息，用于 SQL 生成"""
        sql = """
            SELECT m.name AS table_name, p.name AS column_name,
                   p.type AS column_type, p.pk AS is_pk
            FROM sqlite_master m
            JOIN pragma_table_info(m.name) p
            WHERE m.type='table' AND m.name NOT LIKE 'sqlite_%'
            ORDER BY m.name, p.cid
        """
        return self.execute(sql)
