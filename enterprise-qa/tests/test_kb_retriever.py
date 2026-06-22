"""KB 检索器测试（BM25 + 向量双通道）"""

import os
import tempfile
from pathlib import Path

import pytest

from enterprise_qa.config import Config
from enterprise_qa.kb_retriever import (
    BM25Retriever,
    DocumentChunk,
    HybridRetriever,
    _load_knowledge_docs,
    _tokenize,
)


@pytest.fixture
def sample_chunks():
    return [
        DocumentChunk(doc_id="1", content="考勤制度：月累计迟到3次以内不扣款",
                       source_file="hr_policies.md", section="迟到规则"),
        DocumentChunk(doc_id="2", content="年假：入职满1年享5天，每增1年+1天，上限15天",
                       source_file="hr_policies.md", section="请假类型"),
        DocumentChunk(doc_id="3", content="晋升条件：P5→P6需连续2季度KPI≥85",
                       source_file="promotion_rules.md", section="P5→P6"),
        DocumentChunk(doc_id="4", content="技术栈：Python 3.10+, FastAPI, PostgreSQL",
                       source_file="tech_docs.md", section="技术栈"),
        DocumentChunk(doc_id="5", content="报销标准：酒店一线城市≤500元/天",
                       source_file="finance_rules.md", section="报销标准"),
    ]


@pytest.fixture
def sample_kb_dir():
    """创建临时知识库目录"""
    with tempfile.TemporaryDirectory() as tmp:
        kb_path = Path(tmp)
        # 创建几个 markdown 文件
        (kb_path / "hr_policies.md").write_text(
            "# 人事制度\n\n"
            "## 迟到规则\n月累计迟到3次以内：不扣款\n月累计迟到4-6次：每次扣款50元\n\n"
            "## 请假类型\n年假：入职满1年享5天，每增1年+1天，上限15天\n"
        )
        (kb_path / "promotion_rules.md").write_text(
            "# 晋升标准\n\n"
            "## P5→P6\n"
            "- 入职满1年\n- 连续2季度KPI≥85\n- 主导或核心参与项目≥3个\n"
        )
        yield str(kb_path)


class TestDocumentLoading:
    def test_load_knowledge_docs(self, sample_kb_dir):
        """加载知识库文档"""
        chunks = _load_knowledge_docs(sample_kb_dir)
        assert len(chunks) > 0
        assert all(isinstance(c, DocumentChunk) for c in chunks)

    def test_load_nonexistent_dir(self):
        """加载不存在的目录"""
        with pytest.raises(FileNotFoundError):
            _load_knowledge_docs("/nonexistent/path")


class TestTokenizer:
    def test_tokenize_chinese(self):
        """中文分词"""
        tokens = _tokenize("考勤制度")
        assert len(tokens) > 0
        assert "考" in tokens
        assert "勤" in tokens

    def test_tokenize_mixed(self):
        """中英混合分词"""
        tokens = _tokenize("Python开发")
        assert "python" in tokens
        assert any(c in tokens for c in ["开", "发"])

    def test_tokenize_empty(self):
        """空文本"""
        tokens = _tokenize("")
        assert tokens == []


class TestBM25Retriever:
    def test_search_found(self, sample_chunks):
        """BM25 检索-找到结果"""
        retriever = BM25Retriever(sample_chunks)
        results = retriever.search("迟到怎么扣钱", top_k=3)
        assert len(results) > 0
        # 应该匹配到迟到规则
        scores = [r.bm25_score for r in results]
        assert all(s > 0 for s in scores)

    def test_search_not_found(self, sample_chunks):
        """BM25 检索-无匹配"""
        retriever = BM25Retriever(sample_chunks)
        results = retriever.search("zxywqnotexist", top_k=3)
        assert len(results) == 0

    def test_search_all_chunks(self, sample_chunks):
        """BM25 检索不同主题"""
        retriever = BM25Retriever(sample_chunks)
        # 年假查询
        results = retriever.search("年假怎么算", top_k=2)
        assert len(results) > 0
        # 晋升查询
        results2 = retriever.search("晋升条件是什么", top_k=2)
        assert len(results2) > 0


class TestHybridRetriever:
    def test_bm25_only_mode(self, sample_kb_dir):
        """hybrid 模式（向量不可用时降级 BM25）"""
        cfg = Config()
        cfg.knowledge_base.root_path = sample_kb_dir
        cfg.knowledge_base.index_type = "bm25"

        retriever = HybridRetriever(cfg)
        assert len(retriever.chunks) > 0

        results = retriever.search("年假")
        assert len(results) > 0

    def test_hybrid_mode_available(self, sample_kb_dir):
        """hybrid 模式（本地 embedding 模型可用时使用双通道）"""
        cfg = Config()
        cfg.knowledge_base.root_path = sample_kb_dir
        cfg.knowledge_base.index_type = "hybrid"

        retriever = HybridRetriever(cfg)
        # 本地 transformers 模型可用时，向量通道应可用
        if retriever.vector_available:
            assert retriever.qdrant is not None

        results = retriever.search("迟到")
        assert len(results) > 0

    def test_search_different_queries(self, sample_kb_dir):
        """不同查询的检索效果"""
        cfg = Config()
        cfg.knowledge_base.root_path = sample_kb_dir
        cfg.knowledge_base.index_type = "bm25"

        retriever = HybridRetriever(cfg)

        queries = ["年假", "迟到", "晋升", "报销", "技术栈"]
        for q in queries:
            results = retriever.search(q, top_k=3)
            assert isinstance(results, list)

    def test_get_document_by_source(self, sample_kb_dir):
        """按源文件获取文档块"""
        cfg = Config()
        cfg.knowledge_base.root_path = sample_kb_dir

        retriever = HybridRetriever(cfg)
        chunks = retriever.get_document_by_source("hr_policies.md")
        assert len(chunks) > 0
        assert all(c.source_file == "hr_policies.md" for c in chunks)
