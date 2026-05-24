"""测试知识库的意图识别与回复生成"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge import (
    answer, detect_intent, detect_reason,
    REASON_ILLNESS, REASON_EMERGENCY, REASON_CONFLICT, REASON_FORCE_MAJEURE,
)


def test_detect_reason_illness():
    assert detect_reason("我生病了发烧38度") == REASON_ILLNESS
    assert detect_reason("住院了不能去考试") == REASON_ILLNESS


def test_detect_reason_emergency():
    assert detect_reason("家里出了急事") == REASON_EMERGENCY
    assert detect_reason("父亲突发车祸") == REASON_EMERGENCY


def test_detect_reason_conflict():
    assert detect_reason("两门考试时间冲突了") == REASON_CONFLICT


def test_detect_reason_force_majeure():
    assert detect_reason("因为疫情封控不能去考试") == REASON_FORCE_MAJEURE


def test_detect_intent_materials():
    assert detect_intent("缓考需要提交什么材料？") == "materials"


def test_detect_intent_steps():
    assert detect_intent("缓考流程是怎样的？") == "steps"


def test_detect_intent_deadline():
    assert detect_intent("缓考截止日期是什么时候？") == "deadline"


def test_detect_intent_multi():
    assert detect_intent("我有三门课要缓考") == "multi"


def test_detect_intent_compare():
    assert detect_intent("缓考和补考有什么区别？") == "compare"


def test_detect_intent_missed():
    assert detect_intent("我已经缺考了怎么办？") == "missed"


def test_answer_illness_materials():
    r = answer("我生病了，缓考需要什么材料？")
    assert "诊断证明" in r["answer"]
    assert "materials_list" in r["skills"]


def test_answer_general():
    r = answer("你好")
    assert "缓考助手" in r["answer"]
    assert r["intent"] == "general"


def test_answer_multi_exam():
    r = answer("我有四门课都要缓考怎么办")
    assert "每门" in r["answer"]
    assert "multi_exam_defer" in r["skills"]


def test_answer_compare():
    r = answer("缓考和重修有什么区别？")
    assert "缓考" in r["answer"] and "重修" in r["answer"]


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: ERROR {type(e).__name__}: {e}")
            failed += 1
    print(f"\n  共 {passed + failed} 项，通过 {passed}，失败 {failed}")
    sys.exit(0 if failed == 0 else 1)
