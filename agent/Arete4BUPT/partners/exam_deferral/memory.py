"""
轻量会话记忆模块
按 session_id 保存最近 N 轮对话，支持多轮上下文。
"""

import time
from collections import defaultdict, deque
from typing import Optional


class ConversationMemory:
    def __init__(self, max_turns: int = 6, ttl_seconds: int = 1800):
        self._store: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_turns))
        self._touched: dict[str, float] = {}
        self.ttl = ttl_seconds

    def add(self, session_id: str, role: str, content: str) -> None:
        self._gc()
        self._store[session_id].append({"role": role, "content": content})
        self._touched[session_id] = time.time()

    def get(self, session_id: Optional[str]) -> list[dict]:
        if not session_id:
            return []
        self._gc()
        return list(self._store.get(session_id, []))

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._touched.pop(session_id, None)

    def _gc(self) -> None:
        now = time.time()
        expired = [s for s, t in self._touched.items() if now - t > self.ttl]
        for s in expired:
            self.clear(s)


# 全局单例
memory = ConversationMemory()
