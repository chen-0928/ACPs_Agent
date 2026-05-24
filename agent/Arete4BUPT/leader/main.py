"""Arete4BUPT Leader Agent — 个人课程助手 (FastAPI)"""

from pathlib import Path
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import uvicorn

from assistant.orchestrator import orchestrate
from assistant.session import get_session_manager, TaskStatus

ROOT = Path(__file__).parent

app = FastAPI(title="Arete4BUPT Leader", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class UserRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "agent": "Arete4BUPT Leader"}


@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = ROOT / "static" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse("<h1>Arete4BUPT Leader</h1><p>Chat UI 未找到</p>")


@app.post("/api/v1/submit")
async def submit(req: UserRequest):
    """接收学生提问 → 后台启动 5 阶段编排，立即返回 task_id 供前端轮询."""
    sm = get_session_manager()
    session = sm.get_or_create(req.session_id)
    task = session.create_task()
    session.history.append({"role": "user", "content": req.message})
    task.status = TaskStatus.RUNNING
    task.stage = "intent"
    asyncio.create_task(orchestrate(session.id, req.message, task.id))
    return {
        "session_id": session.id,
        "task_id": task.id,
        "status": "processing",
    }


@app.get("/api/v1/result/{session_id}")
def get_result(session_id: str):
    """轮询任务状态和结果."""
    sm = get_session_manager()
    session = sm._sessions.get(session_id)
    if not session or not session.active_task_id:
        raise HTTPException(status_code=404, detail="会话不存在")

    task = session.tasks.get(session.active_task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "session_id": session.id,
        "active_task_id": session.active_task_id,
        "status": task.status,
        "stage": task.stage,
        "message": (
            task.final_answer
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            else task.clarification or "正在处理..."
        ),
        "task_detail": task.to_dict(),
    }


# 静态资源
STATIC_DIR = ROOT / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=59210, reload=True)
