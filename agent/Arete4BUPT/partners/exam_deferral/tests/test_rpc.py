"""测试 /rpc 端点 (AIP 协议) - 启动 server 后通过 HTTP 调用"""

import sys
import time
import json
import httpx
from pathlib import Path

BASE_URL = "http://localhost:8001"


def wait_for_server(timeout: int = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def call_rpc(query: str, task_id: str = "test-001", session_id: str | None = None) -> dict:
    payload = {
        "task_id": task_id,
        "sender_id": "test-leader",
        "receiver_id": "deferred-exam-partner",
        "query": query,
    }
    if session_id:
        payload["context"] = {"session_id": session_id}

    r = httpx.post(f"{BASE_URL}/rpc", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def test_health():
    r = httpx.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert data["agent_id"] == "deferred-exam-partner"


def test_discover():
    r = httpx.get(f"{BASE_URL}/discover")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "online"
    assert "eligibility_check" in data["skills"]


def test_acs():
    r = httpx.get(f"{BASE_URL}/acs")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"] == "deferred-exam-partner"
    assert len(data["skills"]) >= 6


def test_rpc_illness():
    result = call_rpc("因病无法参加考试，怎么申请缓考？")
    assert result["status"] == "done"
    assert result["agent_id"] == "deferred-exam-partner"
    assert "诊断证明" in result["answer"] or "缓考" in result["answer"]


def test_rpc_materials():
    result = call_rpc("缓考需要提交什么材料？", task_id="test-mat")
    assert result["status"] == "done"
    assert "申请表" in result["answer"]


def test_rpc_multi_exam():
    result = call_rpc("我有三门课要缓考", task_id="test-multi")
    assert result["status"] == "done"
    assert "每门" in result["answer"] or "多门" in result["answer"]


def test_rpc_session_memory():
    """多轮对话：第二轮应能接续上下文"""
    sid = "test-session-001"
    r1 = call_rpc("我生病了", task_id="t1", session_id=sid)
    r2 = call_rpc("那需要什么材料？", task_id="t2", session_id=sid)
    assert r1["status"] == "done"
    assert r2["status"] == "done"


def test_footprint_logs():
    r = httpx.get(f"{BASE_URL}/footprint")
    assert r.status_code == 200
    data = r.json()
    assert "logs" in data
    assert len(data["logs"]) > 0


if __name__ == "__main__":
    if not wait_for_server():
        print("✗ Server 未启动 (http://localhost:8001)")
        print("  请先在另一个终端运行: python main.py")
        sys.exit(1)

    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = failed = 0
    print(f"\n  开始测试 {len(tests)} 个端点...\n")
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  共 {passed + failed} 项，通过 {passed}，失败 {failed}")
    sys.exit(0 if failed == 0 else 1)
