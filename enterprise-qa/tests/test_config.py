"""配置模块测试"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from enterprise_qa.config import load_config


class TestConfig:
    def test_default_config(self):
        """测试默认配置"""
        cfg = load_config()
        assert cfg.database.type == "sqlite"
        assert cfg.database.path != ""
        assert cfg.knowledge_base.root_path != ""
        assert cfg.knowledge_base.index_type in ("bm25", "vector", "hybrid")

    def test_env_override(self):
        """测试环境变量覆盖"""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(yaml.dump({
                "database": {"type": "sqlite", "path": "/tmp/test.db"},
            }))
            os.environ["ENTERPRISE_QA_DB_PATH"] = "/tmp/env-override.db"
            try:
                cfg = load_config(str(config_path))
                assert cfg.database.path == "/tmp/env-override.db"
            finally:
                del os.environ["ENTERPRISE_QA_DB_PATH"]

    def test_yaml_override(self):
        """测试 YAML 文件覆盖默认值"""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(yaml.dump({
                "database": {"type": "sqlite", "path": "/tmp/custom.db"},
                "knowledge_base": {"root_path": "/tmp/custom_kb", "index_type": "bm25"},
            }))
            cfg = load_config(str(config_path))
            assert cfg.database.path == "/tmp/custom.db"
            assert cfg.knowledge_base.root_path == "/tmp/custom_kb"
            assert cfg.knowledge_base.index_type == "bm25"

    def test_index_type_values(self):
        """测试所有 index_type 选项"""
        for it in ("bm25", "vector", "hybrid"):
            cfg = load_config()
            cfg.knowledge_base.index_type = it
            assert cfg.knowledge_base.index_type == it

    def test_embedding_config_defaults(self):
        """测试向量嵌入配置默认值"""
        cfg = load_config()
        # config.yaml 中设置 mode=local，验证从 yaml 正确加载
        assert cfg.embedding.mode == "local"
        assert cfg.embedding.dimension == 512
