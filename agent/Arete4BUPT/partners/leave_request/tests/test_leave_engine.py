from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leave_engine import analyze_leave_request


def test_sick_leave_complete_info_success() -> None:
    result = analyze_leave_request(
        "我发烧了，想从5月14日到5月16日请三天病假。",
        {"student_name": "张三", "student_id": "20240001"},
    )

    assert result["status"] == "success"
    assert result["data"]["leave_type"] == "sick_leave"


def test_official_leave_competition_success() -> None:
    result = analyze_leave_request(
        "我要参加大学生创新创业比赛，5月20日到5月22日和课程冲突，想申请公假。",
        {
            "student_name": "李四",
            "student_id": "20240002",
            "activity_name": "大学生创新创业比赛",
            "organizer": "学校创新创业学院",
        },
    )

    assert result["status"] == "success"
    assert result["data"]["leave_type"] == "official_leave"


def test_missing_information_need_more_info() -> None:
    result = analyze_leave_request("我想请假", {})

    assert result["status"] == "need_more_info"
    assert result["missing_fields"]
    assert result["next_questions"]


def test_non_leave_request_rejected() -> None:
    result = analyze_leave_request("帮我推荐一门人工智能课程", {})

    assert result["status"] == "rejected"
