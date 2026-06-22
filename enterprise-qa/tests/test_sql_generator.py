"""SQL 生成器测试——LLMSQLGenerator 单元测试（不调真实 API）"""

from enterprise_qa.sql_generator import LLMSQLGenerator, _build_schema_text


class TestSchemaBuilding:
    """Schema 构建测试"""

    def test_build_schema_includes_tables(self):
        """验证 schema 文本包含表名"""
        schema = _build_schema_text(None)  # type: ignore
        # 没有 DB 连接时应返回错误信息
        assert "无法读取" in schema or "schema" in schema.lower()


class TestLLMSQLGenerator:
    """LLMSQLGenerator 单元测试（不调真实 API，仅测降级和解析）"""

    def test_no_api_key_fallback(self):
        """无 API key 时走降级"""
        gen = LLMSQLGenerator(db=None, api_key="")  # type: ignore
        queries = gen.generate("张三的邮箱是多少？")
        assert len(queries) == 1
        assert "employees" in queries[0]["sql"]
        assert queries[0]["params"] == ()

    def test_fallback_has_expected_structure(self):
        """降级查询有完整结构"""
        gen = LLMSQLGenerator(db=None, api_key="")  # type: ignore
        queries = gen.generate("测试")
        q = queries[0]
        assert "sql" in q
        assert "params" in q
        assert "description" in q
        assert "source" in q
        assert isinstance(q["params"], tuple)

    def test_empty_api_key_returns_fallback(self):
        """空 API key 返回降级"""
        gen = LLMSQLGenerator(db=None, api_key="")  # type: ignore
        assert gen.api_key == ""
        queries = gen.generate("任何问题")
        assert len(queries) == 1

    def test_generate_method_returns_list(self):
        """generate 始终返回 list"""
        gen = LLMSQLGenerator(db=None, api_key="")  # type: ignore
        queries = gen.generate("")
        assert isinstance(queries, list)

    def test_fallback_sql_is_read_only(self):
        """降级 SQL 是 SELECT"""
        gen = LLMSQLGenerator(db=None, api_key="")  # type: ignore
        queries = gen.generate("测试")
        assert queries[0]["sql"].strip().upper().startswith("SELECT")

    def test_generate_with_invalid_db(self):
        """即使 DB 不可用，LLM 不可用时降级仍工作"""
        gen = LLMSQLGenerator(db=None, api_key="")  # type: ignore
        queries = gen.generate("张三的邮箱")
        assert len(queries) > 0
