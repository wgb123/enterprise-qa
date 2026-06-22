"""会话存储——维护多轮对话历史，支持持久化"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Message:
    """单条消息"""
    role: str  # "user" | "assistant"
    content: str
    reasoning: Optional[str] = None
    traces: Optional[list[dict]] = None
    sources: Optional[list[str]] = None


@dataclass
class Conversation:
    """一次会话，保存消息历史"""
    messages: list[Message] = field(default_factory=list)
    max_turns: int = 20

    def add_user(self, text: str) -> None:
        self.messages.append(Message(role="user", content=text))

    def add_assistant(self, text: str, reasoning: str = "",
                      traces: list | None = None, sources: list | None = None) -> None:
        self.messages.append(Message(
            role="assistant", content=text,
            reasoning=reasoning or None,
            traces=traces or None,
            sources=sources or None,
        ))

    def get_context(self, window: int = 3) -> str:
        """返回最近 N 轮对话作为上下文"""
        recent = self.messages[-(window * 2):]
        lines = []
        for msg in recent:
            prefix = "用户" if msg.role == "user" else "助手"
            lines.append(f"{prefix}: {msg.content}")
        return "\n".join(lines)

    def get_title(self) -> str:
        """第一条用户消息作为会话标题"""
        for msg in self.messages:
            if msg.role == "user":
                return msg.content[:30]
        return "(空)"

    def trim(self) -> None:
        if len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-(self.max_turns * 2):]

    def to_dict(self) -> dict:
        return {"messages": [asdict(m) for m in self.messages]}

    @classmethod
    def from_dict(cls, data: dict) -> Conversation:
        msgs = [Message(**m) for m in data.get("messages", [])]
        return Conversation(messages=msgs)


class ConversationStore:
    """内存会话存储 + 文件持久化"""

    def __init__(self, storage_path: str = ""):
        self._store: dict[str, Conversation] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._storage_path = Path(storage_path) if storage_path else Path("data") / "conversations.json"

    # ── 读写 ──

    def get_or_create(self, conv_id: str) -> tuple[str, Conversation]:
        with self._lock:
            if not conv_id:
                conv_id = uuid.uuid4().hex[:12]
            if conv_id not in self._store:
                self._store[conv_id] = Conversation()
            return conv_id, self._store[conv_id]

    def get(self, conv_id: str) -> Optional[Conversation]:
        return self._store.get(conv_id)

    def delete(self, conv_id: str) -> bool:
        with self._lock:
            if conv_id in self._store:
                del self._store[conv_id]
                self._dirty = True
                return True
            return False

    def list_all(self) -> list[dict]:
        """返回会话列表（id + 标题 + 消息数 + 最后消息预览）"""
        items = []
        for cid, conv in self._store.items():
            preview = ""
            if conv.messages:
                last = conv.messages[-1]
                preview = last.content[:60]
                if last.role == "user":
                    preview = "问: " + preview
                else:
                    preview = "答: " + preview
            items.append({
                "id": cid,
                "title": conv.get_title(),
                "count": len(conv.messages) // 2,
                "preview": preview,
            })
        items.sort(key=lambda x: x["count"], reverse=True)
        return items

    # ── 持久化 ──

    def load(self) -> None:
        """从文件加载会话"""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            with self._lock:
                for cid, conv_data in data.items():
                    self._store[cid] = Conversation.from_dict(conv_data)
        except Exception:
            pass

    def save(self) -> None:
        """保存到文件"""
        with self._lock:
            if not self._dirty:
                return
            data = {cid: conv.to_dict() for cid, conv in self._store.items()}
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._dirty = False

    def mark_dirty(self) -> None:
        self._dirty = True
