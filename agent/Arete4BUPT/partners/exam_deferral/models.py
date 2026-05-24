"""AIP 协议数据模型 - TaskCommand / TaskResult"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    DONE = "done"
    FAILED = "failed"


class TaskCommand(BaseModel):
    """Leader 发给 Partner 的任务指令"""
    task_id: str = Field(..., description="任务唯一标识")
    sender_id: str = Field(..., description="发送方 Agent ID (Leader)")
    receiver_id: str = Field(..., description="接收方 Agent ID (Partner)")
    intent: str = Field(default="", description="意图分类")
    query: str = Field(..., description="用户原始问题")
    context: Optional[dict] = Field(default=None, description="上下文信息")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class TaskResult(BaseModel):
    """Partner 返回给 Leader 的任务结果"""
    task_id: str = Field(..., description="对应的任务 ID")
    agent_id: str = Field(..., description="处理该任务的 Agent ID")
    status: TaskStatus = Field(default=TaskStatus.DONE)
    answer: str = Field(..., description="回复内容")
    metadata: Optional[dict] = Field(default=None, description="附加元数据：产出物等")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
