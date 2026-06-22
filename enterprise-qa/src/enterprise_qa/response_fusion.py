"""结果融合——逐步流式执行，每步产出 SSE 事件

yield (event_type, data_dict) 元组，最终 return 完整回答。
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any

import requests

from enterprise_qa.db_connector import DBConnector, DatabaseError
from enterprise_qa.intent_classifier import IntentResult
from enterprise_qa.kb_retriever import HybridRetriever, SearchResult
from enterprise_qa.sql_generator import LLMSQLGenerator


_ANSWER_PROMPT = """你是一个企业智能问答助手。根据以下查询结果，用自然语言回答用户的问题。

## 回答要求
1. 用简洁的中文自然语言回答，不要 dump 原始数据
2. 如果数据不足，明确说明，不编造
3. 对于混合查询（晋升评估等），用表格对比条件和实际情况

## 用户问题
{question}

## 数据库查询结果
{db_results}

## 知识库检索结果
{kb_results}

## 输出格式
只输出最终回答的纯文本，不要 JSON，不要 markdown 代码块。
不要在回答中包含"来源"标注——系统会自动添加。"""


class ResponseFusion:
    """多源结果融合器（流式）"""

    def __init__(self, db: DBConnector, kb: HybridRetriever,
                 llm_api_base: str = "", llm_api_key: str = "", llm_model: str = ""):
        self.db = db
        self.kb = kb
        self.sql_gen = LLMSQLGenerator(
            db=db,
            api_base=llm_api_base,
            api_key=llm_api_key,
            model=llm_model,
        )
        self.llm_api_base = (llm_api_base or "https://api.deepseek.com/v1").rstrip("/")
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model or "deepseek-chat"

    def answer(self, intent: IntentResult) -> tuple[str, list[tuple[str, dict]]]:
        """非流式包装——收集所有事件，返回 (回答文本, 事件列表)"""
        trace: list[tuple[str, dict]] = []
        gen = self.answer_stream(intent)
        try:
            while True:
                event_type, data = next(gen)
                trace.append((event_type, data))
        except StopIteration as e:
            return e.value or "", trace

    def answer_stream(self, intent: IntentResult) -> Generator[tuple[str, dict], None, str]:
        """流式执行查询，逐步产出事件

        Yields:
            ("reasoning", {text, query_type})
            ("trace", {step, content, ...})
            ("answer_chunk", {token})          # LLM 逐 token 流式输出
            ("answer_done", {sources})         # 流式结束，附带来源
        最终 return: 完整回答文本（含来源标注）
        """
        sources: list[str] = []

        # ---- 推理说明 ----
        if intent.reasoning:
            yield ("reasoning", {
                "text": intent.reasoning,
                "query_type": intent.query_type.value,
            })

        yield ("trace", {"step": "intent", "content": f"意图: {intent.query_type.value}"})

        # ---- 1. SQL 查询 ----
        db_results: list[dict[str, Any]] = []
        if intent.has_db_intent:
            yield ("trace", {"step": "sql_generate", "content": "LLM 根据 schema 生成 SQL..."})
            queries = self.sql_gen.generate(intent.original_question)
            if not queries:
                yield ("trace", {"step": "sql_fallback", "content": "SQL 生成失败，使用降级查询"})
            else:
                yield ("trace", {"step": "sql_generated", "content": f"生成 {len(queries)} 条 SQL"})

            for q in queries:
                try:
                    rows = self.db.execute(q["sql"], q["params"])
                    desc = q.get("description", "")
                    yield ("trace", {
                        "step": "sql_execute",
                        "content": desc,
                        "rows_count": len(rows),
                    })
                    if rows:
                        db_results.append({"query": q, "rows": rows})
                        src = q.get("source", "")
                        if src and src not in sources:
                            sources.append(src)
                except DatabaseError as e:
                    yield ("trace", {"step": "sql_error", "content": str(e)})
                    db_results.append({"query": q, "error": str(e)})
        else:
            yield ("trace", {"step": "sql_skip", "content": "无需数据库查询"})

        # ---- 2. 知识库检索 ----
        kb_results: list[SearchResult] = []
        if intent.has_kb_intent:
            yield ("trace", {"step": "kb_search", "content": "知识库 BM25+向量检索中..."})
            kb_results = self.kb.search(intent.original_question, top_k=5)
            if kb_results:
                files = list(set(r.chunk.source_file for r in kb_results))
                yield ("trace", {
                    "step": "kb_found",
                    "content": f"命中 {len(kb_results)} 个文档块",
                    "files": files,
                })
                for r in kb_results:
                    src = r.chunk.source_file
                    section = r.chunk.section
                    source_str = f"{src} §{section}" if section else src
                    if source_str not in sources:
                        sources.append(source_str)
            else:
                yield ("trace", {"step": "kb_empty", "content": "知识库未匹配到相关内容"})
        else:
            yield ("trace", {"step": "kb_skip", "content": "无需知识库查询"})

        # ---- 3. 序列化 + LLM 流式生成 ----
        db_text = self._serialize_db_results(db_results)
        kb_text = self._serialize_kb_results(kb_results)

        if not db_text and not kb_text:
            yield ("trace", {"step": "done", "content": "无结果"})
            return "抱歉，没有找到相关信息。"

        yield ("trace", {"step": "llm_format", "content": "LLM 逐 token 生成回答..."})

        prompt = _ANSWER_PROMPT.format(
            question=intent.original_question,
            db_results=db_text or "（无数据库结果）",
            kb_results=kb_text or "（无知识库结果）",
        )

        # 流式调用 LLM，逐 token yield
        full_text = ""
        for token in self._call_llm_stream(prompt):
            full_text += token
            yield ("answer_chunk", {"token": token})

        # LLM 不可用时走降级
        if not full_text:
            full_text = self._format_raw(db_text, kb_text, sources)
            yield ("answer_chunk", {"token": full_text})

        # 清理 + 追加来源
        full_text = re.sub(r'\n*> 来源[：:].*$', '', full_text, flags=re.MULTILINE).strip()
        if sources:
            src_parts = []
            for s in sources:
                s = s.strip()
                if s and s not in src_parts:
                    src_parts.append(s)
            if src_parts:
                source_line = "\n\n> 来源: " + " | ".join(src_parts)
                full_text += source_line
                yield ("answer_chunk", {"token": source_line})

        yield ("answer_done", {"sources": sources})
        return full_text

    # ── LLM 流式调用（SSE stream=True） ──

    def _call_llm_stream(self, prompt: str) -> Generator[str, None, None]:
        """调用 LLM 流式 API，逐 token yield 文本内容"""
        if not self.llm_api_key:
            return

        try:
            resp = requests.post(
                f"{self.llm_api_base}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 800,
                    "stream": True,
                },
                headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                stream=True,
                timeout=30,
            )
            resp.raise_for_status()

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                # SSE 格式：data: {...}
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

        except requests.RequestException:
            return

    # ── 降级非流式 LLM 调用（备用） ──

    def _call_llm(self, prompt: str) -> str | None:
        """非流式 LLM 调用（降级备用）"""
        if not self.llm_api_key:
            return None
        try:
            resp = requests.post(
                f"{self.llm_api_base}/chat/completions",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 800,
                },
                headers={
                    "Authorization": f"Bearer {self.llm_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=25,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return None

    # ── 序列化 ──

    def _serialize_db_results(self, db_results: list[dict]) -> str:
        parts = []
        for r in db_results:
            if "error" in r:
                continue
            desc = r["query"].get("description", "")
            rows = r["rows"]
            if not rows:
                continue
            if desc:
                parts.append(f"### {desc}")
            for row in rows[:20]:
                items = ", ".join(f"{k}={v}" for k, v in row.items() if v is not None)
                parts.append(f"  - {items}")
        return "\n".join(parts)

    def _serialize_kb_results(self, kb_results: list[SearchResult]) -> str:
        seen = set()
        parts = []
        for r in kb_results:
            c = r.chunk
            key = f"{c.source_file}§{c.section}"
            if key not in seen:
                seen.add(key)
                parts.append(f"### {c.source_file} §{c.section}")
            parts.append(c.content.strip())
        return "\n".join(parts)

    def _format_raw(self, db_text: str, kb_text: str, sources: list[str]) -> str:
        parts = []
        if db_text:
            parts.append(db_text.replace("### ", "").replace("  - ", "- "))
        if kb_text:
            parts.append(kb_text.replace("### ", ""))
        return "\n\n".join(parts)
