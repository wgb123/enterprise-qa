"""配置管理 - 支持 YAML 文件 + 环境变量覆盖"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    type: str = "sqlite"
    path: str = "./enterprise.db"


class KnowledgeBaseConfig(BaseModel):
    root_path: str = "./knowledge"
    index_type: Literal["bm25", "vector", "hybrid"] = "hybrid"


class LLMConfig(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


class EmbeddingConfig(BaseModel):
    """向量嵌入配置——支持 API 或本地模型"""
    mode: Literal["api", "local"] = "api"
    # API 模式
    provider: str = "openai"
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "text-embedding-3-small"
    # 本地模型模式（需要安装 sentence-transformers）
    local_model: str = "BAAI/bge-small-zh-v1.5"
    dimension: int = 512


class Config(BaseModel):
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    knowledge_base: KnowledgeBaseConfig = Field(default_factory=KnowledgeBaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    timezone: str = "Asia/Shanghai"


def load_config(path: str | None = None) -> Config:
    """加载配置，优先级：环境变量 > YAML 文件 > 默认值"""
    cfg = Config()

    # 1. 尝试从 YAML 文件加载
    config_paths = []
    if path:
        config_paths.append(Path(path))
    config_paths.extend([
        Path.cwd() / "config.yaml",
        Path(__file__).parent.parent.parent / "config.yaml",
    ])

    for cp in config_paths:
        if cp.exists():
            with open(cp, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data:
                _update_from_dict(cfg, data)
            break

    # 2. 环境变量覆盖
    env_map = {
        "ENTERPRISE_QA_DB_PATH": ("database", "path"),
        "ENTERPRISE_QA_KB_PATH": ("knowledge_base", "root_path"),
        "ENTERPRISE_QA_LLM_API_KEY": ("llm", "api_key"),
        "ENTERPRISE_QA_LLM_API_BASE": ("llm", "api_base"),
        "ENTERPRISE_QA_LLM_MODEL": ("llm", "model"),
        "ENTERPRISE_QA_EMBEDDING_API_KEY": ("embedding", "api_key"),
        "ENTERPRISE_QA_EMBEDDING_API_BASE": ("embedding", "api_base"),
        "ENTERPRISE_QA_EMBEDDING_MODEL": ("embedding", "model"),
        "ENTERPRISE_QA_INDEX_TYPE": ("knowledge_base", "index_type"),
    }
    for env_name, (section, field) in env_map.items():
        val = os.environ.get(env_name)
        if val:
            setattr(getattr(cfg, section), field, val)

    # 3. 解析相对路径
    cfg.database.path = str(_resolve_path(cfg.database.path))
    cfg.knowledge_base.root_path = str(_resolve_path(cfg.knowledge_base.root_path))

    return cfg


def _resolve_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _update_from_dict(cfg: Config, data: dict) -> None:
    for section, values in data.items():
        if hasattr(cfg, section) and isinstance(values, dict):
            section_cfg = getattr(cfg, section)
            for key, val in values.items():
                if hasattr(section_cfg, key) and val is not None:
                    # 解析 ${VAR_NAME} 环境变量占位符
                    if isinstance(val, str):
                        val = _resolve_env_var(val)
                    existing = getattr(section_cfg, key)
                    if isinstance(existing, int) and isinstance(val, str):
                        try:
                            val = int(val)
                        except ValueError:
                            val = str(val)
                    elif isinstance(existing, str) and not isinstance(val, str):
                        val = str(val)
                    setattr(section_cfg, key, val)


def _resolve_env_var(val: str) -> str:
    """将 ${VAR_NAME} 替换为环境变量值，未设置则返回原样"""
    def _replace(m: re.Match) -> str:
        var_name = m.group(1)
        # 兼容 VLLM_API_KEY 和 DEEPSEEK_API_KEY
        if var_name == "DEEPSEEK_API_KEY":
            env_val = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("VLLM_API_KEY")
            return env_val if env_val else m.group(0)
        env_val = os.environ.get(var_name)
        return env_val if env_val else m.group(0)
    return re.sub(r'\$\{(\w+)\}', _replace, val)
