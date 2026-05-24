from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional


LOCAL_POLICY_NOTE = (
    "以上流程为北邮校园场景下的模拟请假办理指引，具体审批要求以学院、辅导员和学校实际系统通知为准。"
)

LEAVE_TYPES = {
    "sick_leave": {
        "label": "病假",
        "keywords": ["发烧", "生病", "医院", "就诊", "身体不适", "感冒", "手术", "复诊", "病历", "诊断"],
        "required": ["student_name", "student_id", "start_time", "end_time", "reason"],
        "materials": [
            "医院诊断证明或病历",
            "就诊记录",
            "请假申请",
            "如影响课程，需提前告知任课老师",
            "如时间较长，需联系辅导员或学院学生工作办公室",
        ],
        "approval_flow": [
            "学生提交请假申请",
            "辅导员初审",
            "学院审核",
            "通知相关任课教师",
            "学生按要求补交证明材料或销假",
        ],
        "risk_notes": [
            "病假材料需真实有效，不要伪造诊断证明或病历。",
            "如请假时间较长，可能需要学院进一步审核，具体以实际通知为准。",
        ],
    },
    "personal_leave": {
        "label": "事假",
        "keywords": ["家庭事务", "家里有事", "个人事务", "个人紧急事务", "回家", "私事", "行程冲突"],
        "required": ["student_name", "student_id", "start_time", "end_time", "reason"],
        "materials": [
            "请假申请",
            "相关说明材料，如行程凭证、家庭事务说明等",
            "如影响课程，需提前联系任课老师说明",
        ],
        "approval_flow": [
            "学生说明请假原因",
            "提交申请",
            "辅导员审核",
            "学院视请假时长和原因决定是否进一步审核",
            "通知任课教师",
        ],
        "risk_notes": [
            "事假理由要具体、真实、合规。",
            "不要编造证明材料；过长事假需以学院实际审批为准。",
        ],
    },
    "official_leave": {
        "label": "公假",
        "keywords": ["竞赛", "比赛", "活动", "会议", "志愿", "学校组织", "指导老师", "参赛", "学术会议", "答辩", "挑战杯", "大创"],
        "required": [
            "student_name",
            "student_id",
            "activity_name",
            "organizer",
            "start_time",
            "end_time",
            "reason",
        ],
        "materials": [
            "活动通知",
            "参赛证明或参会证明",
            "指导老师证明",
            "组织单位证明",
            "如涉及课程缺勤，需提前告知任课教师",
        ],
        "approval_flow": [
            "学生提交公假申请",
            "附活动通知或组织证明",
            "指导老师/组织单位确认",
            "辅导员审核",
            "学院审批",
            "通知任课教师",
        ],
        "risk_notes": [
            "公假通常需要活动通知、组织单位或指导老师相关证明。",
            "本 Agent 只能生成申请草稿和流程建议，不能保证审批结果。",
        ],
    },
}

FIELD_LABELS = {
    "student_name": "姓名",
    "student_id": "学号",
    "college": "学院",
    "leave_type": "请假类型",
    "reason": "请假原因",
    "start_time": "开始时间",
    "end_time": "结束时间",
    "duration": "请假时长",
    "activity_name": "活动名称",
    "organizer": "组织单位",
    "has_proof": "是否已有证明材料",
    "contact": "联系方式",
    "affected_courses": "受影响课程",
}

NON_LEAVE_HINTS = ["推荐课程", "人工智能课程", "选课", "考试复习", "食堂", "宿舍报修"]
LEAVE_HINTS = ["请假", "病假", "事假", "公假"] + [
    keyword for item in LEAVE_TYPES.values() for keyword in item["keywords"]
]


def analyze_leave_request(command: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    context = context or {}
    text = _merge_text(command, context)

    if not _is_leave_related(text):
        return _rejected_result()

    extracted = extract_fields(command, context)
    leave_type = extracted.get("leave_type") or detect_leave_type(text)
    if leave_type:
        extracted["leave_type"] = leave_type

    if not extracted.get("reason"):
        extracted["reason"] = _extract_reason(command, leave_type)

    if leave_type == "official_leave":
        extracted.setdefault("activity_name", _extract_activity_name(command))

    rule = LEAVE_TYPES.get(leave_type or "", {})
    required_fields = list(rule.get("required", ["student_name", "student_id", "leave_type", "start_time", "end_time", "reason"]))
    if not leave_type and "leave_type" not in required_fields:
        required_fields.insert(0, "leave_type")

    missing_fields = [field for field in required_fields if not extracted.get(field)]
    completeness_score = _completeness_score(required_fields, missing_fields)
    next_questions = build_next_questions(missing_fields, leave_type)
    draft_application = generate_draft(extracted, leave_type)

    data = {
        "leave_type": leave_type,
        "leave_type_label": rule.get("label", "待判断"),
        "completeness_score": completeness_score,
        "extracted_fields": extracted,
        "required_materials": rule.get("materials", _default_materials()),
        "approval_flow": rule.get("approval_flow", _default_flow()),
        "draft_application": draft_application,
        "reminders": _build_reminders(extracted, leave_type),
        "risk_notes": rule.get("risk_notes", ["信息不足时请先补充，不要假装已经完成请假提交。"]),
        "next_questions": next_questions,
        "local_policy_note": LOCAL_POLICY_NOTE,
    }

    status = "need_more_info" if missing_fields else "success"
    summary = (
        "已完成请假需求分析，但还需要补充关键信息。"
        if status == "need_more_info"
        else f"已按北邮校园场景模拟规则生成{rule.get('label', '请假')}办理建议和申请草稿。"
    )
    return {
        "status": status,
        "summary": summary,
        "data": data,
        "missing_fields": missing_fields,
        "next_questions": next_questions,
        "error": None,
    }


def extract_fields(command: str, context: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for key in FIELD_LABELS:
        value = context.get(key)
        if value not in (None, "", []):
            fields[key] = value

    source_agent_name = context.get("source_agent_name")
    source_aic = context.get("source_aic")
    if source_agent_name:
        fields["source_agent_name"] = source_agent_name
    if source_aic:
        fields["source_aic"] = source_aic

    fields.setdefault("student_name", _match_first(command, [r"姓名[:：]?\s*([\u4e00-\u9fa5]{2,4})", r"我是([\u4e00-\u9fa5]{2,4})"]))
    fields.setdefault("student_id", _match_first(command, [r"学号[:：]?\s*([A-Za-z0-9\-]{4,})", r"\b(20\d{6,12})\b"]))
    fields.setdefault("college", _match_first(command, [r"([\u4e00-\u9fa5]{2,20}学院)"]))
    fields.setdefault("contact", _match_first(command, [r"(?:电话|手机|联系方式)[:：]?\s*([0-9\-]{7,})"]))

    start_time, end_time = _extract_time_range(command)
    fields.setdefault("start_time", start_time)
    fields.setdefault("end_time", end_time)
    fields.setdefault("duration", _match_first(command, [r"请([一二两三四五六七八九十\d]+天)", r"([一二两三四五六七八九十\d]+天)"]))

    if "证明" in command or "病历" in command or "通知" in command:
        fields.setdefault("has_proof", True)
    if "课程冲突" in command or "不能上课" in command or "缺勤" in command:
        fields.setdefault("affected_courses", "涉及课程缺勤或课程冲突")

    return {key: value for key, value in fields.items() if value not in (None, "", [])}


def detect_leave_type(text: str) -> Optional[str]:
    scores = {}
    for leave_type, rule in LEAVE_TYPES.items():
        scores[leave_type] = sum(1 for keyword in rule["keywords"] if keyword in text)

    explicit_map = {"病假": "sick_leave", "事假": "personal_leave", "公假": "official_leave"}
    for keyword, leave_type in explicit_map.items():
        if keyword in text:
            scores[leave_type] = scores.get(leave_type, 0) + 3

    best_type, best_score = max(scores.items(), key=lambda item: item[1])
    return best_type if best_score > 0 else None


def build_next_questions(missing_fields: List[str], leave_type: Optional[str]) -> List[str]:
    questions = []
    for field in missing_fields:
        label = FIELD_LABELS.get(field, field)
        if field == "leave_type":
            questions.append("请问你要申请病假、事假还是公假？")
        elif field == "reason":
            questions.append("请补充具体、真实、合规的请假原因。")
        elif field == "start_time":
            questions.append("请补充请假的开始时间。")
        elif field == "end_time":
            questions.append("请补充请假的结束时间。")
        elif field == "activity_name":
            questions.append("请补充公假对应的活动、竞赛或会议名称。")
        elif field == "organizer":
            questions.append("请补充活动组织单位或指导老师信息。")
        else:
            questions.append(f"请补充{label}。")

    if leave_type == "sick_leave":
        questions.append("如果已有医院诊断证明、病历或就诊记录，也可以一并说明。")
    return questions


def generate_draft(fields: Dict[str, Any], leave_type: Optional[str]) -> str:
    leave_label = LEAVE_TYPES.get(leave_type or "", {}).get("label", "请假")
    college = fields.get("college", "【待补充】")
    name = fields.get("student_name", "【待补充】")
    student_id = fields.get("student_id", "【待补充】")
    reason = fields.get("reason", "【待补充】")
    start_time = fields.get("start_time", "【待补充】")
    end_time = fields.get("end_time", "【待补充】")
    today = date.today().isoformat()

    if leave_type == "official_leave":
        activity = fields.get("activity_name", "【待补充】")
        organizer = fields.get("organizer", "【待补充】")
        reason_text = f"因参加{organizer}组织的{activity}，{reason}"
    else:
        reason_text = f"因{reason}"

    return (
        "尊敬的老师：\n"
        f"您好！我是{college}{name}，学号{student_id}。{reason_text}，需要于{start_time}至{end_time}申请{leave_label}。"
        "请假期间我将主动与任课教师沟通课程安排，并按要求补交相关证明材料。\n"
        "恳请批准。\n"
        f"申请人：{name}\n"
        f"日期：{today}"
    )


def _is_leave_related(text: str) -> bool:
    if any(hint in text for hint in NON_LEAVE_HINTS) and not any(hint in text for hint in LEAVE_HINTS):
        return False
    return any(hint in text for hint in LEAVE_HINTS)


def _rejected_result() -> Dict[str, Any]:
    summary = "本 Agent 只处理病假、事假、公假等校园请假流程，暂不处理该类请求。"
    return {
        "status": "rejected",
        "summary": summary,
        "data": {
            "leave_type": None,
            "leave_type_label": None,
            "completeness_score": 0,
            "extracted_fields": {},
            "required_materials": [],
            "approval_flow": [],
            "draft_application": "",
            "reminders": ["如需办理请假，请说明请假类型、时间、原因、姓名和学号。"],
            "risk_notes": ["本 Agent 不处理休学咨询、课程推荐或其他非请假事项。"],
            "next_questions": [],
            "local_policy_note": LOCAL_POLICY_NOTE,
        },
        "missing_fields": [],
        "next_questions": [],
        "error": None,
    }


def _merge_text(command: str, context: Dict[str, Any]) -> str:
    context_text = " ".join(str(value) for value in context.values() if value is not None)
    return f"{command} {context_text}"


def _match_first(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _extract_time_range(text: str) -> tuple[Optional[str], Optional[str]]:
    patterns = [
        r"从?(\d{1,2}月\d{1,2}日)\s*(?:到|至|-|—)\s*(\d{1,2}月\d{1,2}日)",
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s*(?:到|至|-|—)\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        r"于?([^\s，,。]{2,12})\s*(?:到|至)\s*([^\s，,。]{2,12})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1), match.group(2)
    return None, None


def _extract_reason(command: str, leave_type: Optional[str]) -> Optional[str]:
    for pattern in [r"因(.+?)(?:，|,|。|需要|想|申请|请假)", r"因为(.+?)(?:，|,|。|需要|想|申请|请假)"]:
        match = re.search(pattern, command)
        if match:
            return match.group(1).strip()

    if leave_type == "sick_leave":
        for keyword in LEAVE_TYPES["sick_leave"]["keywords"]:
            if keyword in command:
                return keyword
    if leave_type == "personal_leave":
        for keyword in LEAVE_TYPES["personal_leave"]["keywords"]:
            if keyword in command:
                return keyword
        match = re.search(r"参加(.+?)(?:，|,|。|想|需要|申请|请假)", command)
        if match:
            return f"参加{match.group(1).strip()}"
    if leave_type == "official_leave":
        return "活动安排与课程时间冲突" if "课程冲突" in command else "参加学校或组织相关活动"
    return None


def _extract_activity_name(command: str) -> Optional[str]:
    match = re.search(r"参加(.+?(?:比赛|竞赛|会议|活动|答辩))", command)
    return match.group(1).strip() if match else None


def _completeness_score(required_fields: List[str], missing_fields: List[str]) -> int:
    if not required_fields:
        return 100
    return round((len(required_fields) - len(missing_fields)) / len(required_fields) * 100)


def _default_materials() -> List[str]:
    return ["请假申请", "请假原因说明", "必要时提供相关证明材料"]


def _default_flow() -> List[str]:
    return ["学生补充请假信息", "提交申请", "辅导员审核", "学院按实际情况处理", "通知任课教师"]


def _build_reminders(fields: Dict[str, Any], leave_type: Optional[str]) -> List[str]:
    reminders = [
        "请假申请应在提交前核对姓名、学号、时间和原因。",
        "本 Agent 不会替你真实提交申请，请按学院或学校系统要求完成提交。",
    ]
    if fields.get("affected_courses"):
        reminders.append("如涉及课程缺勤，请提前向任课教师说明并确认补课或作业安排。")
    if leave_type == "official_leave":
        reminders.append("公假建议准备活动通知、参赛证明、指导老师或组织单位证明。")
    return reminders
