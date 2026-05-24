"""调用 Partner 智能体的 AIP RPC 端点."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# 确保能导入项目根目录的 footprint_sdk
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from footprint_sdk import report_call

logger = logging.getLogger(__name__)

# Partner 地址映射表
PARTNER_ENDPOINTS: dict[str, str] = {
    "选课助手":   "http://localhost:59221/rpc",
    "请假助手":   "http://localhost:59222/rpc",
    "考试提醒助手": "http://localhost:59224/rpc",
}

TIMEOUT_SECONDS = 120
LEADER_ID = "leader-agent"
LEADER_NAME = "个人课程助手Leader"
LEADER_AIC = "1.2.156.3088.0001.00001.R1JUQE.821HRL.1.0YVV"

# Partner AIC 映射
PARTNER_AICS: dict[str, str] = {
    "选课助手":   "1.2.156.3088.0001.00001.D614VG.000000.1.04CH",
    "请假助手":   "1.2.156.3088.0001.00001.HBQ3SF.F7JHGG.1.07HK",
    "考试提醒助手": "1.2.156.3088.0001.00001.E3GP7C.E6A4I1.1.0HJ7",
}


def _build_external_body(partner_name: str, task_id: str, payload: dict) -> dict:
    """为跨组外部 Agent 构造通用 JSON-RPC 请求体."""
    message = payload.get("message", "")
    return {
        "jsonrpc": "2.0",
        "method": "rpc",
        "id": task_id,
        "params": {
            "command": {
                "type": "task-command",
                "id": task_id,
                "sentAt": datetime.now(timezone.utc).isoformat(),
                "senderRole": "leader",
                "senderId": LEADER_ID,
                "command": "start",
                "taskId": task_id,
                "dataItems": [{"type": "text", "text": message}],
                "sessionId": task_id,
            }
        },
    }


def _build_body(partner_name: str, task_id: str, payload: dict) -> dict:
    """为不同 Partner 构造对应的请求体格式."""
    message = payload.get("message", "")

    if partner_name == "选课助手":
        return {"task_id": task_id, "command": "start", "payload": payload}

    if partner_name == "请假助手":
        return {
            "task_id": task_id,
            "command": "start",
            "source_agent_name": LEADER_NAME,
            "source_aic": LEADER_AIC,
            "target_agent_name": "请假助手",
            "target_aic": PARTNER_AICS["请假助手"],
            "context": {"message": message, **{k: v for k, v in payload.items() if k != "message"}},
        }

    if partner_name == "考试提醒助手":
        return {
            "jsonrpc": "2.0",
            "method": "rpc",
            "id": task_id,
            "params": {
                "command": {
                    "type": "task-command",
                    "id": task_id,
                    "sentAt": datetime.now(timezone.utc).isoformat(),
                    "senderRole": "leader",
                    "senderId": LEADER_ID,
                    "command": "start",
                    "taskId": task_id,
                    "dataItems": [{"type": "text", "text": message}],
                    "sessionId": task_id,
                }
            },
        }

    # fallback: generic format
    return {"task_id": task_id, "command": "start", "payload": payload}


async def call_partner(partner_name: str, task_id: str, payload: dict,
                       endpoint: str = None, external: bool = False) -> dict:
    """向指定 Partner 发送任务（协作前上报 Footprint），返回结果 dict。"""
    url = endpoint or PARTNER_ENDPOINTS.get(partner_name)
    dest_aic = PARTNER_AICS.get(partner_name, "UNKNOWN")
    if not url:
        return {
            "error": f"未知 Partner: {partner_name}",
            "available": list(PARTNER_ENDPOINTS.keys()),
        }

    if external:
        body = _build_external_body(partner_name, task_id, payload)
    else:
        body = _build_body(partner_name, task_id, payload)

    logger.info("→ %s  %s", partner_name, url)

    # ★ 协作前上报 Footprint（SDK 标准格式）
    await report_call(LEADER_NAME, LEADER_AIC, partner_name, dest_aic)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            result = resp.json()
            logger.info("← %s  status=%s", partner_name, result.get("status", "?"))
            return result
    except httpx.TimeoutException:
        logger.warning("← %s  timeout", partner_name)
        return {"error": f"{partner_name} 请求超时", "status": "failed"}
    except Exception as e:
        logger.warning("← %s  error: %s", partner_name, e)
        return {"error": str(e), "status": "failed"}
