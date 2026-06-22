#!/usr/bin/env python3
"""企业智能问答助手 - HTTP 服务器（SSE 流式输出，逐步展示思考过程）"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from enterprise_qa.config import load_config
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

STATIC_DIR = Path(__file__).resolve().parent / "static"


class QAHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/ask":
            self._handle_ask(parsed)
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

    def _handle_ask(self, parsed):
        params = parse_qs(parsed.query)
        question = params.get("q", [""])[0].strip()
        if not question:
            self._send_json({"error": "请输入问题"}, 400)
            return

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

        try:
            # Step 1: 意图分类
            emit("trace", {"step": "classify", "content": "分析问题意图..."})
            intent = classify_intent(question, llm_classifier=llm_clf)

            # Step 2: 流式执行（逐 token 实时推送）
            gen = fusion.answer_stream(intent)
            try:
                while True:
                    event_type, data = next(gen)
                    emit(event_type, data)
            except StopIteration:
                pass

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
    server = HTTPServer(("0.0.0.0", port), QAHandler)
    print(f"http://localhost:{port}")
    print("Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止")
        server.server_close()


if __name__ == "__main__":
    main()
