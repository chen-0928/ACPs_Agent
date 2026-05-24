"""
ACPs Footprint SDK — Async 封装
供 Leader 和 Partner 在协作前上报调用信息到态势感知大屏

用法:
    from footprint_sdk import report_call
    await report_call(src_name, src_aic, dest_name, dest_aic)
"""

import asyncio

import httpx

FOOTPRINT_URL = "http://117.74.66.90:8006/notify"
TIMEOUT = 3.0


async def report_call(
    src_name: str,
    src_aic: str,
    dest_name: str,
    dest_aic: str,
) -> bool:
    """
    向 Footprint 大屏上报一次智能体间的调用关系。
    必须在协作发生前调用，不阻塞主流程。
    返回 True/False 表示上报是否成功。
    """
    payload = {
        "AgentName_src": src_name,
        "src_AIC": src_aic,
        "AgentName_dist": dest_name,
        "dest_AIC": dest_aic,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(FOOTPRINT_URL, json=payload)
            resp.raise_for_status()
            return True
    except Exception:
        return False  # 上报失败绝对不能影响业务


def report_call_sync(
    src_name: str,
    src_aic: str,
    dest_name: str,
    dest_aic: str,
) -> bool:
    """同步版本，供非 async 代码使用"""
    try:
        return asyncio.run(report_call(src_name, src_aic, dest_name, dest_aic))
    except Exception:
        return False
