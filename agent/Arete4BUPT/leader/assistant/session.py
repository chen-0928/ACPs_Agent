"""会话和任务状态管理（内存存储，开发阶段使用）."""

import uuid
import time
from dataclasses import dataclass, field
from typing import Optional, Union


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    intent: dict = field(default_factory=dict)
    subtasks: list = field(default_factory=list)
    results: list = field(default_factory=list)
    final_answer: str = ""
    status: str = TaskStatus.PENDING
    stage: str = ""            # 当前阶段: intent/discovery/planning/executing/aggregating
    clarification: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.id,
            "status": self.status,
            "stage": self.stage,
            "clarification": self.clarification,
            "subtasks": [s.get("partner_name", "") for s in self.subtasks],
            "final_answer": self.final_answer,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Session:
    id: str
    history: list = field(default_factory=list)
    tasks: dict[str, Task] = field(default_factory=dict)
    active_task_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def create_task(self) -> Task:
        task = Task(id=str(uuid.uuid4())[:8])
        self.tasks[task.id] = task
        self.active_task_id = task.id
        return task


class SessionManager:
    """内存存储，重启丢失（生产环境可换 Redis/DB）."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: Optional[str] = None) -> Session:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        sid = session_id or str(uuid.uuid4())[:8]
        session = Session(id=sid)
        self._sessions[sid] = session
        return session


_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _instance
    if _instance is None:
        _instance = SessionManager()
    return _instance
