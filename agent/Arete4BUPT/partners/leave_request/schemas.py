from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskCommand(BaseModel):
    task_id: str
    source_agent_name: Optional[str] = None
    source_aic: Optional[str] = None
    target_agent_name: Optional[str] = None
    target_aic: Optional[str] = None
    user_id: Optional[str] = None
    command: str
    context: Dict[str, Any] = Field(default_factory=dict)


class TaskResult(BaseModel):
    task_id: str
    status: str
    agent_name: str
    agent_aic: str
    summary: str
    data: Dict[str, Any] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    next_questions: List[str] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class LeaveAnalyzeRequest(BaseModel):
    command: str
    context: Dict[str, Any] = Field(default_factory=dict)


class LeaveDraftRequest(BaseModel):
    command: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
