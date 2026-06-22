#!/usr/bin/env python3
"""企业智能问答助手 - HTTP 服务器（SSE 流式输出，逐步展示思考过程）"""

from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from enterprise_qa.config import load_config
from enterprise_qa.conversation import ConversationStore
from enterprise_qa.db_connector import DBConnector
from enterprise_qa.intent_classifier import LLMIntentClassifier, classify_intent
from enterprise_qa.kb_retriever import HybridRetriever
from enterprise_qa.response_fusion import ResponseFusion

# ── 全局初始化（单例） ──────────────────────────────
config = load_config()
db = DBConnector(config)
kb = HybridRetriever(config)
llm_clf = LLMIntentClassifier(
    api_base=config.llm.api_base,
    api_key=config.llm.api_key,
    model=config.llm.model,
) if config.llm.api_key else None
fusion = ResponseFusion(
    db, kb,
    llm_api_base=config.llm.api_base,
    llm_api_key=config.llm.api_key,
    llm_model=config.llm.model,
)

# 会话存储（持久化）
conv_store = ConversationStore(storage_path="data/conversations.json")
conv_store.load()

STATIC_DIR = Path(__file__).resolve().parent / "static"


class QAHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/ask":
            self._handle_ask(parsed)
        elif path == "/api/conversations":
            self._handle_conversations()
        elif path == "/api/conversation":
            self._handle_conversation(params)
        elif path == "/api/conversation/delete":
            self._handle_delete_conversation(params)
        elif path == "/":
            self._serve_file("index.html")
        else:
            file_path = path.lstrip("/")
            if file_path and (STATIC_DIR / file_path).exists():
                self._serve_file(file_path)
            else:
                self._serve_file("index.html")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _serve_file(self, filename: str):
        filepath = STATIC_DIR / filename
        if not filepath.exists():
            self.send_error(404)
            return

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime_map = {
            "html": "text/html; charset=utf-8",
            "css": "text/css; charset=utf-8",
            "js": "application/javascript",
            "json": "application/json",
            "png": "image/png",
            "svg": "image/svg+xml",
            "ico": "image/x-icon",
        }
        self.send_response(200)
        self.send_header("Content-Type", mime_map.get(ext, "application/octet-stream"))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with open(filepath, "rb") as f:
            self.wfile.write(f.read())

    def _handle_conversations(self):
        """返回会话列表"""
        self._send_json({"data": conv_store.list_all()})

    def _handle_conversation(self, params):
        """返回单个会话的消息历史（含思考过程、步骤追踪、来源）"""
        cid = params.get("id", [""])[0]
        conv = conv_store.get(cid)
        if not conv:
            self._send_json({"error": "会话不存在"}, 404)
            return
        messages = []
        for m in conv.messages:
            item = {"role": m.role, "content": m.content}
            if m.role == "assistant":
                if m.reasoning:
                    item["reasoning"] = m.reasoning
                if m.traces:
                    item["traces"] = m.traces
                if m.sources:
                    item["sources"] = m.sources
            messages.append(item)
        self._send_json({"id": cid, "messages": messages})

    def _handle_delete_conversation(self, params):
        cid = params.get("id", [""])[0]
        ok = conv_store.delete(cid)
        conv_store.save()
        self._send_json({"ok": ok})

    def _handle_ask(self, parsed):
        params = parse_qs(parsed.query)
        question = params.get("q", [""])[0].strip()
        conv_id = params.get("conv_id", [""])[0].strip()
        if not question:
            self._send_json({"error": "请输入问题"}, 400)
            return

        # 获取会话上下文
        conv_id, conv = conv_store.get_or_create(conv_id)
        history_context = conv.get_context(window=2)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def emit(event_type: str, data: dict):
            """发送一条 SSE 事件"""
            try:
                payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()
            except BrokenPipeError:
                raise

        # 先保存用户问题（确保 conv_id 发出时 title 已就绪）
        conv.add_user(question)

        # 发会话 ID，Web UI 靠它保持同一会话
        emit("conv_id", {"id": conv_id})

        try:
            # Step 1: 意图分类（带上历史上下文）
            emit("trace", {"step": "classify", "content": "分析问题意图..."})
            intent = classify_intent(question, llm_classifier=llm_clf, history=history_context)

            # Step 2: 流式执行（逐 token 实时推送）
            stream_answer = ""
            reasoning_text = ""
            trace_steps: list[dict] = []
            source_list: list[str] = []
            gen = fusion.answer_stream(intent, history=history_context)
            try:
                while True:
                    event_type, data = next(gen)
                    emit(event_type, data)
                    if event_type == "reasoning":
                        reasoning_text = data.get("text", "")
                    elif event_type == "trace":
                        trace_steps.append(data)
                    elif event_type == "answer_chunk":
                        stream_answer += data.get("token", "")
                    elif event_type == "answer_done":
                        source_list = data.get("sources", [])
            except StopIteration:
                pass

            # 记录助手回答到会话历史（含思考过程、步骤、来源）
            if stream_answer:
                clean = re.sub(r"\n*> 来源: .*", "", stream_answer).strip()
                conv.add_assistant(clean, reasoning=reasoning_text,
                                   traces=trace_steps, sources=source_list)
                conv.trim()
                conv_store.mark_dirty()
                conv_store.save()

            # 流式结束
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self.wfile.write(
                    f'data: {{"type":"error","text":"{str(e)}"}}\n\n'.encode()
                )
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except BrokenPipeError:
                pass

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, fmt, *args):
        if "/api/" in str(args[0]):
            super().log_message(fmt, *args)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = ThreadingHTTPServer(("0.0.0.0", port), QAHandler)
    print(f"http://localhost:{port}")
    print("Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止")
        server.server_close()


if __name__ == "__main__":
    main()
