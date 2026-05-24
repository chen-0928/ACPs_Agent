"""
ADP 动态发现模块
向 ACPs Agent Discovery Server 发送自然语言查询，获取匹配的 Agent 列表及 endPoints。
"""

import logging

import httpx

logger = logging.getLogger(__name__)

DISCOVERY_URL = "http://117.74.66.90:8005/acps-adp-v2/discover"
TIMEOUT = 15


async def discover_agents(query: str, limit: int = 5) -> list[dict]:
    """
    向 ADP 发现服务器查询匹配的智能体。
    返回: [{"aic": ..., "name": ..., "endpoint": ..., "skills": [...]}, ...]
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(DISCOVERY_URL, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("ADP 发现失败: %s，回退到硬编码", e)
        return []

    acs_map = data.get("result", {}).get("acsMap", {})
    agents = []
    for aic, info in acs_map.items():
        if not info.get("active"):
            continue

        eps = info.get("endPoints", [])
        endpoint = eps[0].get("url", "") if eps else ""

        agents.append({
            "aic": aic,
            "name": info.get("name", ""),
            "description": info.get("description", ""),
            "endpoint": endpoint,
            "skills": [s.get("name", "") for s in info.get("skills", [])],
        })

    logger.info("ADP 发现: query=%r → %d agents", query[:40], len(agents))
    return agents[:limit]
