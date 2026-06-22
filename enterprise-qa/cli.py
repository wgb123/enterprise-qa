#!/usr/bin/env python3
"""企业智能问答助手 - CLI 入口"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保能找到 src/
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from enterprise_qa.config import load_config
from enterprise_qa.db_connector import DBConnector
from enterprise_qa.intent_classifier import LLMIntentClassifier, classify_intent
from enterprise_qa.kb_retriever import HybridRetriever
from enterprise_qa.response_fusion import ResponseFusion


def main():
    config = load_config()

    # 初始化各模块
    print(f"🔌 数据库: {config.database.path}")
    print(f"📚 知识库: {config.knowledge_base.root_path}")
    print(f"🔍 检索模式: {config.knowledge_base.index_type}")

    # LLM 意图分类器
    llm_classifier = None
    if config.llm.api_key or config.embedding.api_key:
        llm_classifier = LLMIntentClassifier(
            api_base=config.llm.api_base,
            api_key=config.llm.api_key or config.embedding.api_key,
            model=config.llm.model,
        )
        print("🧠 意图识别: LLM (DeepSeek)")

    try:
        db = DBConnector(config)
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        sys.exit(1)

    kb = HybridRetriever(config)
    print(f"📄 文档块数: {len(kb.chunks)}")
    if kb.vector_available:
        print("✅ 向量通道: 可用")
    else:
        print("⚠️  向量通道: 不可用（仅 BM25 检索）")

    fusion = ResponseFusion(
        db, kb,
        llm_api_base=config.llm.api_base,
        llm_api_key=config.llm.api_key or config.embedding.api_key,
        llm_model=config.llm.model,
    )
    print("🧠 SQL 生成: LLM (DeepSeek)")

    # 交互式问答
    print("\n" + "=" * 50)
    print("  企业智能问答助手 v0.1")
    print("  输入问题，输入 /quit 退出")
    print("=" * 50)

    while True:
        try:
            q = input("\n❓ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not q:
            continue
        if q.lower() in ("/quit", "/exit", "/q"):
            break

        # 意图识别
        intent = classify_intent(q, llm_classifier=llm_classifier)
        print(f"\n[意图] {intent.query_type.value}")
        if intent.entities:
            print(f"[实体] {intent.entities}")
        if intent.reasoning:
            print(f"[推理] {intent.reasoning}")

        # 流式执行——逐 token 实时输出
        gen = fusion.answer_stream(intent)
        answer_parts: list[str] = []
        try:
            while True:
                event_type, data = next(gen)
                if event_type == "trace":
                    print(f"  [{data.get('step', '')}] {data.get('content', '')}")
                elif event_type == "answer_chunk":
                    token = data.get("token", "")
                    print(token, end="", flush=True)
                    answer_parts.append(token)
                elif event_type == "answer_done":
                    pass  # 流式结束
        except StopIteration as e:
            answer = e.value or ""
        # 如果没有流式 token（降级路径），直接打印完整回答
        if not answer_parts:
            print(f"\n{answer}")


def single_query(question: str) -> str:
    """单次查询（供外部调用）"""
    config = load_config()
    llm_classifier = None
    if config.llm.api_key:
        llm_classifier = LLMIntentClassifier(
            api_base=config.llm.api_base,
            api_key=config.llm.api_key,
            model=config.llm.model,
        )
    db = DBConnector(config)
    kb = HybridRetriever(config)
    fusion = ResponseFusion(
        db, kb,
        llm_api_base=config.llm.api_base,
        llm_api_key=config.llm.api_key or config.embedding.api_key,
        llm_model=config.llm.model,
    )
    intent = classify_intent(question, llm_classifier=llm_classifier)
    answer, _ = fusion.answer(intent)
    return answer


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(single_query(" ".join(sys.argv[1:])))
    else:
        main()
