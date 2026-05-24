"""
缓考助手 Partner Agent
基于 FastAPI 的 AIP 协议实现，提供 /rpc 端点接收 Leader 的 TaskCommand
"""

import json
import uvicorn
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from models import TaskCommand, TaskResult, TaskStatus
from llm_client import call_llm, load_config
from memory import memory
from footprint import FootprintMiddleware, read_recent_logs
from atr_client import get_aic


# ─── Agent 元信息 ───
AGENT_ID = "deferred-exam-partner"
AGENT_NAME = "缓考助手"
ROOT = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    port = config["server"]["port"]
    aic = get_aic() or "(未注册，请先运行 python atr_client.py)"
    print(f"\n{'=' * 60}")
    print(f"  {AGENT_NAME}  Partner Agent")
    print(f"{'=' * 60}")
    print(f"  Agent ID:  {AGENT_ID}")
    print(f"  AIC:       {aic}")
    print(f"  监听端口:  {port}")
    print(f"  Web UI:    http://localhost:{port}/")
    print(f"  RPC 端点:  POST /rpc")
    print(f"  ACS 端点:  GET  /acs")
    print(f"  发现端点:  GET  /discover")
    print(f"  Footprint: GET  /footprint")
    print(f"{'=' * 60}\n")
    yield
    print(f"\n[{AGENT_NAME}] Agent 已停止")


app = FastAPI(
    title=AGENT_NAME,
    description="高校缓考申请助手 Partner Agent - ACP实训营",
    version="1.0.0",
    lifespan=lifespan,
)

# Footprint 中间件 - 记录所有 RPC 调用
app.add_middleware(FootprintMiddleware, agent_id=AGENT_ID)


# ─── AIP 协议 /rpc 端点 ───
@app.post("/rpc")
async def handle_rpc(command: TaskCommand) -> JSONResponse:
    """接收 Leader 发来的 TaskCommand，处理后返回 TaskResult"""
    print(f"[RPC] task_id={command.task_id} sender={command.sender_id} query={command.query!r}")

    # 上下文携带 session_id 时启用多轮记忆
    session_id = (command.context or {}).get("session_id") if command.context else None
    history = memory.get(session_id)

    try:
        result_obj = await call_llm(command.query, command.intent, history=history)
        answer_text = result_obj["answer"]

        if session_id:
            memory.add(session_id, "user", command.query)
            memory.add(session_id, "assistant", answer_text)

        result = TaskResult(
            task_id=command.task_id,
            agent_id=AGENT_ID,
            status=TaskStatus.DONE,
            answer=answer_text,
            metadata={
                "intent": result_obj.get("intent", command.intent or "unknown"),
                "reason": result_obj.get("reason", "unknown"),
                "skills_used": result_obj.get("skills", []),
                "source": result_obj.get("source", "unknown"),
                "session_id": session_id,
            },
        )
    except Exception as e:
        print(f"[RPC Error] {e}")
        result = TaskResult(
            task_id=command.task_id,
            agent_id=AGENT_ID,
            status=TaskStatus.FAILED,
            answer=f"处理失败: {str(e)}",
            metadata={"error": str(e)},
        )

    return JSONResponse(content=result.model_dump())


# ─── ACS 能力描述端点 ───
@app.get("/acs")
async def get_acs():
    """返回 Agent 能力描述 (ACS)，供 Leader 通过 ADP 发现"""
    acs_path = ROOT / "acs.json"
    with open(acs_path, "r", encoding="utf-8") as f:
        acs = json.load(f)
    acs["aic"] = get_aic()
    return JSONResponse(content=acs)


# ─── ADP 发现端点 ───
@app.get("/discover")
async def discover():
    """供 Leader 通过 ADP 发现本 Agent"""
    return JSONResponse(content={
        "agent_id": AGENT_ID,
        "name": AGENT_NAME,
        "aic": get_aic(),
        "status": "online",
        "endpoint": "/rpc",
        "skills": [
            "eligibility_check",
            "materials_list",
            "application_guide",
            "deadline_query",
            "multi_exam_defer",
            "scenario_adapt",
        ],
        "timestamp": datetime.now().isoformat(),
    })


# ─── 健康检查 ───
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "agent": AGENT_NAME,
        "agent_id": AGENT_ID,
        "aic": get_aic(),
    }


# ─── Footprint 查询 ───
@app.get("/footprint")
async def footprint_logs(limit: int = 50):
    """查看最近的 Footprint 调用记录"""
    return JSONResponse(content={
        "agent_id": AGENT_ID,
        "logs": read_recent_logs(limit),
    })


# ─── 简易测试端点（方便调试） ───
@app.post("/test")
async def test_query(request: Request):
    """简易测试入口，传 {query, session_id?} 即可"""
    body = await request.json()
    query = body.get("query", "")
    session_id = body.get("session_id")
    if not query:
        return JSONResponse(content={"error": "请提供 query 参数"}, status_code=400)

    history = memory.get(session_id) if session_id else None
    result = await call_llm(query, history=history)

    if session_id:
        memory.add(session_id, "user", query)
        memory.add(session_id, "assistant", result["answer"])

    return JSONResponse(content={
        "query": query,
        "answer": result["answer"],
        "intent": result.get("intent"),
        "reason": result.get("reason"),
        "skills_used": result.get("skills", []),
        "source": result.get("source"),
        "session_id": session_id,
    })


# ─── 静态资源 (Web UI) ───
STATIC_DIR = ROOT / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回 Web Chat 主页"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse(f"<h1>{AGENT_NAME}</h1><p>Web UI 未启用，请使用 /test 或 /rpc 端点</p>")


# ─── 入口 ───
if __name__ == "__main__":
    config = load_config()
    server_cfg = config["server"]
    uvicorn.run(
        "main:app",
        host=server_cfg.get("host", "0.0.0.0"),
        port=server_cfg.get("port", 8001),
        reload=True,
    )
