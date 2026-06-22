"""知识库检索器——BM25 + Qdrant 本地向量双通道 + RRF 融合

向量存储：Qdrant 本地模式（二进制文件，无需服务）
嵌入模型：sentence-transformers 本地加载 BAAI/bge-small-zh-v1.5
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from enterprise_qa.config import Config


# ============================================================
# 数据模型
# ============================================================

@dataclass
class DocumentChunk:
    """文档块"""
    doc_id: str
    content: str
    source_file: str                # 知识库文件路径（相对）
    section: str = ""               # 章节标题
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.doc_id)


@dataclass
class SearchResult:
    chunk: DocumentChunk
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rrf_score: float = 0.0

    @property
    def combined_score(self) -> float:
        return self.rrf_score or max(self.bm25_score, self.vector_score)


# ============================================================
# 文档加载与分块
# ============================================================

def _load_knowledge_docs(root_path: str) -> list[DocumentChunk]:
    """加载知识库文档，分割为带章节的文档块"""
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"知识库目录不存在: {root}")

    chunks: list[DocumentChunk] = []
    chunk_id = 0

    for md_file in sorted(root.rglob("*.md")):
        rel_path = str(md_file.relative_to(root))
        content = md_file.read_text(encoding="utf-8")

        # 按标题（## 或 #）分块
        sections = re.split(r'(?=^#+\s)', content, flags=re.MULTILINE)
        current_section = "概述"

        for section_text in sections:
            section_text = section_text.strip()
            if not section_text:
                continue

            # 提取章节标题
            header_match = re.match(r'^#+\s+(.+)$', section_text, re.MULTILINE)
            if header_match:
                current_section = header_match.group(1).strip()

            # 跳过纯标题块（没有正文内容）
            body = re.sub(r'^#+\s+.*$', '', section_text, flags=re.MULTILINE).strip()
            if len(body) < 10:
                continue

            # 如果正文太长，再按段落分割
            paragraphs = [p.strip() for p in body.split('\n\n') if p.strip()]
            for para in paragraphs:
                if len(para) < 10:
                    continue
                chunks.append(DocumentChunk(
                    doc_id=f"{rel_path}#{current_section}#{chunk_id}",
                    content=para,
                    source_file=rel_path,
                    section=current_section,
                    metadata={"file": rel_path, "heading": current_section},
                ))
                chunk_id += 1

    return chunks


# ============================================================
# 本地嵌入模型（transformers + mean pooling）
# ============================================================

class LocalEmbedder:
    """本地嵌入模型，使用 transformers 加载 BGE/其他模型

    通过 mean pooling 将 token embeddings 聚合为句子向量。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", dimension: int = 512):
        self.model_name = model_name
        self.dimension = dimension
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is None:
            from transformers import AutoModel, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name)
            # 移到 GPU（如果可用）
            import torch
            if torch.cuda.is_available():
                self._model = self._model.cuda()

    def embed(self, texts: list[str]) -> np.ndarray:
        """批量获取文本向量，返回 (n, dim) float32 ndarray"""
        import torch
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.dimension)

        self._load()

        # BGE 模型需要用 "为这个句子生成表示以用于检索相关文章：" 前缀
        # 但 bge-small-zh-v1.5 也可以不用前缀
        inputs = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)
            # mean pooling: 取 last_hidden_state 的均值
            attention_mask = inputs["attention_mask"]
            hidden = outputs.last_hidden_state
            mask_expanded = attention_mask.unsqueeze(-1).expand(hidden.size()).float()
            pooled = (hidden * mask_expanded).sum(1) / mask_expanded.sum(1)

        vecs = pooled.cpu().numpy().astype(np.float32)
        # L2 归一化
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms

    def embed_single(self, text: str) -> np.ndarray:
        """获取单个文本向量，返回 (dim,) float32 ndarray"""
        return self.embed([text])[0]


# ============================================================
# Qdrant 本地向量存储
# ============================================================

class QdrantVectorStore:
    """Qdrant 本地模式向量存储（二进制文件持久化）"""

    COLLECTION_NAME = "enterprise_kb"

    def __init__(self, storage_path: str, embedder: LocalEmbedder):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(path=str(self.storage_path))
        return self._client

    def collection_exists(self) -> bool:
        try:
            self.client.get_collection(self.COLLECTION_NAME)
            return True
        except Exception:
            return False

    def create_collection(self, dimension: int = 512):
        """创建向量集合"""
        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )

    def index_chunks(self, chunks: list[DocumentChunk], force: bool = False):
        """将文档块嵌入并存入 Qdrant

        Args:
            chunks: 文档块列表
            force: 是否强制重建（默认增量，同名 collection 跳过）
        """
        if not chunks:
            return

        if self.collection_exists():
            if not force and self.point_count == len(chunks):
                return  # 已完整索引，跳过
            # 空 collection 或数量不匹配 → 重建
            self.client.delete_collection(self.COLLECTION_NAME)

        self.create_collection(dimension=self.embedder.dimension)

        texts = [c.content for c in chunks]
        vectors = self.embedder.embed(texts)

        points = []
        for i, chunk in enumerate(chunks):
            payload = {
                "doc_id": chunk.doc_id,
                "source_file": chunk.source_file,
                "section": chunk.section,
                "content": chunk.content,
                "metadata": chunk.metadata,
            }
            points.append(PointStruct(id=i, vector=vectors[i].tolist(), payload=payload))

        # 分批上传，每批 100 条
        batch_size = 100
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points[i:i + batch_size],
            )

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """向量检索"""
        if not self.collection_exists():
            return []

        query_vec = self.embedder.embed_single(query)

        results = self.client.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=query_vec.tolist(),
            limit=top_k,
        )

        search_results = []
        for hit in results:
            p = hit.payload or {}
            chunk = DocumentChunk(
                doc_id=p.get("doc_id", ""),
                content=p.get("content", ""),
                source_file=p.get("source_file", ""),
                section=p.get("section", ""),
                metadata=p.get("metadata", {}),
            )
            search_results.append(SearchResult(
                chunk=chunk,
                vector_score=float(hit.score),
            ))
        return search_results

    @property
    def point_count(self) -> int:
        """向量总数"""
        if not self.collection_exists():
            return 0
        info = self.client.get_collection(self.COLLECTION_NAME)
        return info.points_count or 0


# ============================================================
# BM25 检索器
# ============================================================

def _tokenize(text: str) -> list[str]:
    """中文+英文混合分词"""
    text = text.lower()
    tokens = []

    english_tokens = re.findall(r'[a-z0-9+]+', text)
    tokens.extend(english_tokens)

    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    tokens.extend(chinese_chars)

    if len(chinese_chars) >= 2:
        bigrams = [f"{chinese_chars[i]}{chinese_chars[i+1]}"
                   for i in range(len(chinese_chars) - 1)]
        tokens.extend(bigrams)

    return tokens


class BM25Retriever:
    """BM25 关键词检索器"""

    def __init__(self, chunks: list[DocumentChunk]):
        self.chunks = chunks
        self._build_index()

    def _build_index(self):
        tokenized_corpus = [_tokenize(c.content) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        query_tokens = _tokenize(query)
        scores = self.bm25.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append(SearchResult(
                    chunk=self.chunks[idx],
                    bm25_score=float(scores[idx]),
                ))
        return results


# ============================================================
# RRF 混合检索器
# ============================================================

class HybridRetriever:
    """BM25 + Qdrant 向量双通道 + RRF 融合"""

    def __init__(self, config: Config):
        self.config = config
        self.kb_path = config.knowledge_base.root_path
        self.rrf_k: int = 60
        self.index_type = config.knowledge_base.index_type

        # 加载文档
        self.chunks = _load_knowledge_docs(self.kb_path)

        # BM25 通道（始终可用）
        self.bm25 = BM25Retriever(self.chunks)

        # Qdrant 向量通道
        self.qdrant: Optional[QdrantVectorStore] = None
        self._vector_available = False

        if self.index_type in ("hybrid", "vector"):
            self._init_vector_store()

    def _init_vector_store(self):
        """初始化 Qdrant 向量存储（失败时降级 BM25-only）"""
        try:
            embedder = LocalEmbedder(
                model_name=self.config.embedding.local_model,
                dimension=self.config.embedding.dimension,
            )
            qdrant_path = str(Path(self.kb_path).parent / "qdrant_kb")
            self.qdrant = QdrantVectorStore(storage_path=qdrant_path, embedder=embedder)
            self.qdrant.index_chunks(self.chunks)
            self._vector_available = True
        except Exception as e:
            self._vector_available = False
            self.qdrant = None

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """双通道检索 + RRF 融合"""

        if self.index_type == "bm25":
            return self.bm25.search(query, top_k)

        if self.index_type == "vector" and self._vector_available and self.qdrant:
            results = self.qdrant.search(query, top_k)
            return results or self.bm25.search(query, top_k)

        # hybrid 模式：双通道 + RRF
        bm25_results = self.bm25.search(query, top_k * 2)
        vector_results: list[SearchResult] = []
        if self._vector_available and self.qdrant:
            vector_results = self.qdrant.search(query, top_k * 2)

        return self._rrf_fuse(bm25_results, vector_results, top_k)

    def _rrf_fuse(self, results_a: list[SearchResult], results_b: list[SearchResult],
                  top_k: int) -> list[SearchResult]:
        """Reciprocal Rank Fusion"""
        score_map: dict[str, SearchResult] = {}

        for rank, r in enumerate(results_a):
            did = r.chunk.doc_id
            if did not in score_map:
                score_map[did] = r
            score_map[did].rrf_score += 1.0 / (self.rrf_k + rank + 1)

        for rank, r in enumerate(results_b):
            did = r.chunk.doc_id
            if did not in score_map:
                score_map[did] = r
            score_map[did].rrf_score += 1.0 / (self.rrf_k + rank + 1)

        sorted_results = sorted(score_map.values(), key=lambda x: x.rrf_score, reverse=True)
        return sorted_results[:top_k]

    def get_document_by_source(self, source_file: str) -> list[DocumentChunk]:
        """按源文件获取文档块"""
        return [c for c in self.chunks if c.source_file == source_file]

    @property
    def vector_available(self) -> bool:
        return self._vector_available
