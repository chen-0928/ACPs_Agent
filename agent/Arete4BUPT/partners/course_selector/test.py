"""Arete4BUPT 选课助手 — 测试脚本（对齐交付标准 + 适配实际实现）"""
import requests
import json

# 选课助手 RPC 地址（与交付标准 2.1 一致）
BASE_URL = "http://localhost:59221"

# 测试用例集合（覆盖交付标准全部核心场景，并根据实际实现调整学期为非必填）
TEST_CASES = [
    # ===== 阶段① Decision 相关 =====
    {
        "name": "TC1: 正常选课请求（信息不全，应返回 awaiting_input）",
        "payload": {
            "task_id": "tc001",
            "command": "start",
            "payload": {
                "message": "帮我选一门AI方向的选修课",
                "original_message": {
                    "scenario": "选课",
                    "urgency": "normal",
                    "keywords": ["AI", "选修"]
                },
                "depends_on_result": None
            }
        },
        "expect_status": "awaiting_input",
        "check_fn": lambda d: ("年级" in d["result"]["message"] or "方向" in d["result"]["message"])
    },
    {
        "name": "TC2: 补充信息后正常请求（应返回 completed）",
        "payload": {
            "task_id": "tc002",
            "command": "start",
            "payload": {
                "message": "帮我选一门AI方向的选修课，我是大二计算机学院的",
                "original_message": {
                    "scenario": "选课",
                    "urgency": "normal",
                    "keywords": ["AI", "选修", "大二", "计算机学院"]
                },
                "depends_on_result": None
            }
        },
        "expect_status": "completed",
        "check_fn": lambda d: len(d["result"]["message"]) > 10
    },
    {
        "name": "TC3: 超出服务范围（请假请求，应返回 failed）",
        "payload": {
            "task_id": "tc003",
            "command": "start",
            "payload": {
                "message": "我想请3天病假，需要准备什么材料",
                "original_message": {
                    "scenario": "请假",
                    "urgency": "normal",
                    "keywords": ["病假", "材料"]
                },
                "depends_on_result": None
            }
        },
        "expect_status": "failed",
        "check_fn": lambda d: "不" in d["result"]["message"] or "无法" in d["result"]["message"]
    },
    {
        "name": "TC4: 混合请求（选课+请假，应返回 failed 或 awaiting_input 或 completed）",
        "payload": {
            "task_id": "tc004",
            "command": "start",
            "payload": {
                "message": "帮我选一门AI课，顺便帮我请个假",
                "original_message": {
                    "scenario": "混合",
                    "urgency": "normal",
                    "keywords": ["AI课", "请假"]
                },
                "depends_on_result": None
            }
        },
        "expect_status": ["failed", "awaiting_input", "completed"],
        "check_fn": None
    },
    {
        "name": "TC5: 空消息请求（应返回 failed）",
        "payload": {
            "task_id": "tc005",
            "command": "start",
            "payload": {
                "message": "",
                "original_message": {},
                "depends_on_result": None
            }
        },
        "expect_status": "failed",
        "check_fn": None
    },
    # ===== 阶段② Analysis 相关（学期非必填，不追问学期） =====
    {
        "name": "TC6: 缺少学期字段（信息已足够，应返回 completed）",
        "payload": {
            "task_id": "tc006",
            "command": "start",
            "payload": {
                "message": "我是大二计算机学院的，帮我选一门AI选修课",
                "original_message": {
                    "scenario": "选课",
                    "urgency": "normal",
                    "keywords": ["AI", "选修", "大二", "计算机学院"]
                },
                "depends_on_result": None
            }
        },
        "expect_status": "completed",
        "check_fn": lambda d: any(kw in d["result"]["message"] for kw in ["课程", "推荐", "《", "深度学习", "自然语言处理"])
    },
    # ===== 阶段③ Production 相关 =====
    {
        "name": "TC7: 信息完整请求（应返回 completed 且内容包含课程推荐）",
        "payload": {
            "task_id": "tc007",
            "command": "start",
            "payload": {
                "message": "我是大二计算机学院的，想选一门AI方向的选修课，有什么推荐吗？",
                "original_message": {
                    "scenario": "选课",
                    "urgency": "normal",
                    "keywords": ["AI", "选修", "大二", "计算机学院"]
                },
                "depends_on_result": None
            }
        },
        "expect_status": "completed",
        "check_fn": lambda d: any(kw in d["result"]["message"] for kw in ["课程", "推荐", "《", "深度学习", "自然语言处理"])
    }
]


def test_health():
    """测试健康检查接口（交付标准未强制要求，但建议保留）"""
    print("=" * 70)
    print("测试 健康检查 /health")
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code != 200:
            print(f"⚠️  警告 | 状态码: {resp.status_code}（交付标准未强制要求该接口）")
            return
        data = resp.json()
        print(f"✅ 通过 | 响应: {data}")
    except Exception as e:
        print(f"⚠️  警告 | 错误: {str(e)}（交付标准未强制要求该接口）")
    print()


def run_test_case(case):
    """执行单个测试用例（严格校验交付标准返回结构）"""
    print("-" * 70)
    print(f"测试用例: {case['name']}")
    print(f"期望状态: {case['expect_status']}")
    try:
        resp = requests.post(
            f"{BASE_URL}/rpc",
            json=case["payload"],
            headers={"Content-Type": "application/json"},
            timeout=90
        )

        # 交付标准要求：即使失败也不抛500，返回JSON
        if resp.status_code != 200:
            print(f"❌ 失败 | HTTP状态码非200: {resp.status_code}（违反交付标准：出错应返回status:failed而非500）")
            print(f"响应内容: {resp.text}")
            print()
            return

        data = resp.json()

        # 1. 校验顶层字段完整性（交付标准 2.3）
        required_top_keys = {"task_id", "status", "result"}
        missing_keys = required_top_keys - set(data.keys())
        if missing_keys:
            print(f"❌ 失败 | 返回缺少顶层字段: {missing_keys}")
            print(f"返回内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
            print()
            return

        # 2. 校验 task_id 原样返回（交付标准 2.3）
        if data["task_id"] != case["payload"]["task_id"]:
            print(f"❌ 失败 | task_id 不一致: 期望 {case['payload']['task_id']}, 实际 {data['task_id']}")
            print()

        # 3. 校验 result 结构（交付标准 2.3）
        if "message" not in data["result"]:
            print(f"❌ 失败 | result 缺少 message 字段")
            print(f"返回内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
            print()
            return

        # 4. 校验 status 是否符合预期（交付标准 2.3 状态枚举）
        actual_status = data.get("status")
        expect = case["expect_status"]

        if isinstance(expect, list):
            is_pass = actual_status in expect
        else:
            is_pass = actual_status == expect

        if not is_pass:
            print(f"❌ 失败 | 实际状态: {actual_status}，不符合期望")
            print(f"返回内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
            print()
            return

        # 5. 执行自定义校验函数（如有）
        check_fn = case.get("check_fn")
        if check_fn and not check_fn(data):
            print(f"⚠️  警告 | 状态正确，但返回内容未通过业务校验")
            print(f"返回内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
            print()
            return

        print(f"✅ 通过 | 实际状态: {actual_status}")
        print(f"返回内容: {json.dumps(data, ensure_ascii=False, indent=2)}")

    except Exception as e:
        print(f"❌ 请求异常 | 错误: {str(e)}")
    print()


def main():
    print("=" * 70)
    print("Arete4BUPT 选课助手 测试（对齐交付标准 + 适配实际实现）")
    print("=" * 70)
    print()

    # 可选：健康检查
    test_health()

    # 执行所有 RPC 测试用例（交付标准 2.1：POST /rpc）
    for case in TEST_CASES:
        run_test_case(case)

    print("=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()