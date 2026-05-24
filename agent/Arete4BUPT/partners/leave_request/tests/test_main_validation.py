from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app


client = TestClient(app)


def test_acs_exposes_agent_discovery_metadata() -> None:
    response = client.get("/acs")

    body = response.json()
    assert response.status_code == 200
    assert body["agent_code"] == "leave_request_agent"
    assert "leave_application_drafting" in body["skills"]


def test_rpc_supports_direct_agent_call_without_web_ui() -> None:
    response = client.post(
        "/rpc",
        json={
            "task_id": "agent-call-001",
            "source_agent_name": "",
            "source_aic": "",
            "target_agent_name": "校园请假助手",
            "target_aic": "PLEASE_REPLACE_WITH_REAL_AIC",
            "user_id": "student-001",
            "command": "我因发烧，想从2026-05-14到2026-05-16请3天病假，请帮我生成材料清单、审批流程和请假申请。",
            "context": {
                "student_name": "张三",
                "student_id": "2024000101",
                "college": "信息与通信工程学院",
                "leave_type": "sick_leave",
                "reason": "发烧",
                "start_time": "2026-05-14",
                "end_time": "2026-05-16",
                "duration": "3天",
            },
        },
    )

    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["leave_type"] == "sick_leave"
    assert "诊断证明" in " ".join(body["data"]["required_materials"])


def test_rpc_rejects_student_id_shorter_than_10_digits() -> None:
    response = client.post(
        "/rpc",
        json={
            "task_id": "invalid-id-short",
            "source_agent_name": "",
            "source_aic": "",
            "target_agent_name": "校园请假助手",
            "target_aic": "PLEASE_REPLACE_WITH_REAL_AIC",
            "user_id": "student-001",
            "command": "我想请假",
            "context": {
                "student_name": "张三",
                "student_id": "20240001",
                "college": "信息与通信工程学院",
            },
        },
    )

    body = response.json()
    assert body["status"] == "error"
    assert "10 位数字" in body["error"]


def test_rpc_rejects_student_id_longer_than_10_digits() -> None:
    response = client.post(
        "/rpc",
        json={
            "task_id": "invalid-id-long",
            "source_agent_name": "",
            "source_aic": "",
            "target_agent_name": "校园请假助手",
            "target_aic": "PLEASE_REPLACE_WITH_REAL_AIC",
            "user_id": "student-001",
            "command": "我想请假",
            "context": {
                "student_name": "张三",
                "student_id": "20240001011",
                "college": "信息与通信工程学院",
            },
        },
    )

    body = response.json()
    assert body["status"] == "error"
    assert "10 位数字" in body["error"]


def test_rpc_rejects_college_outside_allowed_list() -> None:
    response = client.post(
        "/rpc",
        json={
            "task_id": "invalid-college",
            "source_agent_name": "",
            "source_aic": "",
            "target_agent_name": "校园请假助手",
            "target_aic": "PLEASE_REPLACE_WITH_REAL_AIC",
            "user_id": "student-001",
            "command": "我想请假",
            "context": {
                "student_name": "张三",
                "student_id": "2024000101",
                "college": "不存在学院",
            },
        },
    )

    body = response.json()
    assert body["status"] == "error"
    assert "学院" in body["error"]


def test_rpc_rejects_end_date_before_start_date() -> None:
    response = client.post(
        "/rpc",
        json={
            "task_id": "invalid-date-range",
            "source_agent_name": "",
            "source_aic": "",
            "target_agent_name": "校园请假助手",
            "target_aic": "PLEASE_REPLACE_WITH_REAL_AIC",
            "user_id": "student-001",
            "command": "我想请假",
            "context": {
                "student_name": "张三",
                "student_id": "2024000101",
                "college": "信息与通信工程学院",
                "start_time": "2026-05-16",
                "end_time": "2026-05-14",
            },
        },
    )

    body = response.json()
    assert body["status"] == "error"
    assert "结束日不能早于请假起始日" in body["error"]
