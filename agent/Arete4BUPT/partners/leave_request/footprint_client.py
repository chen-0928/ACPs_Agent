from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import toml


CONFIG_PATH = Path(__file__).with_name("config.toml")
EXAMPLE_CONFIG_PATH = Path(__file__).with_name("config.example.toml")


def load_config() -> Dict[str, Any]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    config: Dict[str, Any] = toml.load(path) if path.exists() else {}
    footprint_url = os.getenv("LEAVE_AGENT_FOOTPRINT_URL") or os.getenv("FOOTPRINT_URL")
    if footprint_url:
        config.setdefault("acps", {})["footprint_url"] = footprint_url
    return config


def get_footprint_url(config: Optional[Dict[str, Any]] = None) -> str:
    config = config or load_config()
    return str(config.get("acps", {}).get("footprint_url", "")).strip()


def notify_call(
    source_name: Optional[str],
    source_aic: Optional[str],
    dest_name: str,
    dest_aic: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = get_footprint_url(config)
    if not url:
        return {"ok": False, "warning": "未配置 footprint_url，已跳过 Footprint 上报。"}

    payload = {
        "AgentName_src": source_name or "UNKNOWN_SOURCE_AGENT",
        "src_AIC": source_aic or "UNKNOWN_SOURCE_AIC",
        "AgentName_dist": dest_name,
        "dest_AIC": dest_aic,
    }
    try:
        response = httpx.post(url, json=payload, timeout=3.0)
        response.raise_for_status()
        return {"ok": True, "status_code": response.status_code}
    except Exception as exc:  # Footprint failure must not fail business flow.
        return {"ok": False, "warning": f"Footprint 上报失败：{exc}"}
