"""
Footprint 上报模块
将每次 RPC 调用的关键信息（task_id / 调用方 / 耗时 / 状态）上报给 Footprint 平台，
便于追踪整个多 Agent 协作链路。
"""

import json
import time
import asyncio
import httpx
from pathlib import Path
from datetime import datetime
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import tomli


CONFIG_PATH = Path(__file__).parent / "config.toml"
LOG_PATH = Path(__file__).parent / "logs" / "footprint.jsonl"


def _load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomli.load(f)


class FootprintMiddleware(BaseHTTPMiddleware):
    """记录每次 HTTP 请求的执行痕迹并上报。"""

    def __init__(self, app, agent_id: str):
        super().__init__(app)
        self.agent_id = agent_id
        config = _load_config().get("footprint", {})
        self.enabled = config.get("enabled", True)
        self.report_url = config.get("report_url", "")
        LOG_PATH.parent.mkdir(exist_ok=True)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)

        start = time.perf_counter()
        ts_start = datetime.now().isoformat()

        # 读取 body（避免消耗后丢失）
        body_bytes = b""
        if request.method == "POST":
            body_bytes = await request.body()

            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            request = Request(request.scope, receive)

        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 解析 task 信息
        task_id = ""
        sender_id = ""
        intent = ""
        if body_bytes:
            try:
                body_json = json.loads(body_bytes)
                task_id = body_json.get("task_id", "")
                sender_id = body_json.get("sender_id", "")
                intent = body_json.get("intent", "")
            except Exception:
                pass

        record = {
            "timestamp": ts_start,
            "agent_id": self.agent_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "elapsed_ms": round(elapsed_ms, 2),
            "task_id": task_id,
            "sender_id": sender_id,
            "intent": intent,
        }

        # 本地落盘
        self._write_local_log(record)
        # 异步上报到 Footprint 平台
        if self.report_url:
            asyncio.create_task(self._report_remote(record))

        return response

    def _write_local_log(self, record: dict) -> None:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Footprint] 本地写日志失败: {e}")

    async def _report_remote(self, record: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(self.report_url, json=record)
        except Exception as e:
            print(f"[Footprint] 远程上报失败: {e}")


def read_recent_logs(limit: int = 50) -> list[dict]:
    """读取最近的 footprint 记录（供 /footprint 端点使用）"""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(records))
