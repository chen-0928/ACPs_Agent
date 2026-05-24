"""
缓考知识库 - 结构化数据 + 场景路由
作为本地兜底逻辑使用，确保即便没有 LLM 也能给出有用回答。
"""

from typing import Optional


# ─── 缓考类型枚举 ───
REASON_ILLNESS = "illness"
REASON_EMERGENCY = "emergency"
REASON_CONFLICT = "conflict"
REASON_FORCE_MAJEURE = "force_majeure"
REASON_UNKNOWN = "unknown"


# ─── 关键词分类器 ───
KEYWORDS = {
    REASON_ILLNESS: ["病", "生病", "住院", "发烧", "感冒", "手术", "受伤", "身体", "诊断", "病历", "病假", "校医院"],
    REASON_EMERGENCY: ["家", "家里", "家人", "亲属", "父亲", "母亲", "去世", "葬礼", "车祸", "事故", "急事", "突发"],
    REASON_CONFLICT: ["冲突", "撞", "同一时间", "两门", "两科", "时间重叠", "同时"],
    REASON_FORCE_MAJEURE: ["地震", "台风", "洪水", "疫情", "封控", "灾", "自然灾害"],
}


# ─── 材料模板 ───
MATERIALS = {
    REASON_ILLNESS: [
        "《缓考申请表》（教务系统下载）",
        "校医院或三甲医院诊断证明原件（建议注明\"不宜参加考试\"）",
        "病历本复印件",
        "学生证复印件",
    ],
    REASON_EMERGENCY: [
        "《缓考申请表》",
        "相关证明材料原件及复印件（事故认定书 / 亲属病危通知 / 死亡证明 等）",
        "辅导员签字的情况说明（加盖学院公章）",
        "学生证复印件",
    ],
    REASON_CONFLICT: [
        "《缓考申请表》",
        "两门课程考试时间冲突的截图证明（教务系统打印盖章）",
        "学生证复印件",
    ],
    REASON_FORCE_MAJEURE: [
        "《缓考申请表》",
        "官方通告或证明文件",
        "辅导员/学院开具的情况说明",
        "学生证复印件",
    ],
}


# ─── 截止时间 ───
DEADLINES = {
    REASON_ILLNESS: "考试前 / 考试当天，特殊情况考后 **3 个工作日内** 补交",
    REASON_EMERGENCY: "考试前 / 考试当天，特殊情况考后 **3 个工作日内** 补交",
    REASON_CONFLICT: "考试前 **5 个工作日** ⚠️ 必须提前申请，错过无法受理",
    REASON_FORCE_MAJEURE: "事件发生后 **5 个工作日内**",
}


# ─── 完整流程 ───
APPLICATION_STEPS = [
    ("下载申请表", "登录教务系统 → 学生服务 → 缓考申请，下载《缓考申请表》"),
    ("填写申请表", "如实填写缓考原因、涉及课程、考试时间等信息"),
    ("准备证明材料", "根据缓考类型准备对应材料（详见材料清单）"),
    ("辅导员签字", "携带申请表与材料找辅导员签字、加盖学院章"),
    ("提交学院教务办", "将完整材料提交至所在学院教务办公室"),
    ("学院审核", "通常 3 个工作日，可在教务系统查询审核进度"),
    ("结果通知", "审核通过后教务系统中该科目状态变为\"缓考\""),
    ("参加缓考", "下学期开学第 2-3 周参加缓考考试，地点见教务通知"),
]


def detect_reason(text: str) -> str:
    """关键词匹配判断缓考类型"""
    text = text.lower()
    scores = {r: 0 for r in KEYWORDS}
    for reason, words in KEYWORDS.items():
        for w in words:
            if w in text:
                scores[reason] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else REASON_UNKNOWN


def detect_intent(text: str) -> str:
    """检测用户意图：资格 / 材料 / 流程 / 截止 / 多门 / 区别 / 通用"""
    t = text.lower()
    if any(k in t for k in ["资格", "条件", "能不能", "可以吗", "符合", "够不够"]):
        return "eligibility"
    if any(k in t for k in ["材料", "准备", "提交什么", "需要什么", "申请表"]):
        return "materials"
    if any(k in t for k in ["流程", "步骤", "怎么申请", "如何申请", "去哪里", "在哪里"]):
        return "steps"
    if any(k in t for k in ["截止", "deadline", "什么时候", "时间节点", "几号"]):
        return "deadline"
    if any(k in t for k in ["多门", "好几门", "几门", "三门", "四门", "批量"]):
        return "multi"
    if any(k in t for k in ["区别", "补考", "重修", "区分", "不一样"]):
        return "compare"
    if any(k in t for k in ["错过", "已经", "缺考", "没考", "没去", "未考"]):
        return "missed"
    return "general"


def render_materials(reason: str) -> str:
    items = MATERIALS.get(reason, MATERIALS[REASON_ILLNESS])
    title = {
        REASON_ILLNESS: "因病缓考",
        REASON_EMERGENCY: "因事缓考",
        REASON_CONFLICT: "考试冲突缓考",
        REASON_FORCE_MAJEURE: "不可抗力缓考",
    }.get(reason, "缓考")
    lines = [f"## {title} - 所需材料\n"]
    for i, m in enumerate(items, 1):
        lines.append(f"{i}. {m}")
    deadline = DEADLINES.get(reason, "")
    if deadline:
        lines.append(f"\n📅 **提交截止**：{deadline}")
    return "\n".join(lines)


def render_steps() -> str:
    lines = ["## 缓考申请完整流程\n"]
    for i, (title, desc) in enumerate(APPLICATION_STEPS, 1):
        lines.append(f"**{i}. {title}**")
        lines.append(f"   {desc}\n")
    lines.append("⚠️ 缓考申请一经批准不可撤销，请确认必要后再提交。")
    return "\n".join(lines)


def render_deadlines() -> str:
    lines = [
        "## 缓考关键时间节点\n",
        "| 缓考类型 | 申请截止 |",
        "|---------|---------|",
    ]
    type_names = {
        REASON_ILLNESS: "因病缓考",
        REASON_EMERGENCY: "因事缓考",
        REASON_CONFLICT: "考试冲突",
        REASON_FORCE_MAJEURE: "不可抗力",
    }
    for r, name in type_names.items():
        lines.append(f"| {name} | {DEADLINES[r]} |")
    lines.append("\n📅 **缓考考试时间**：下学期开学第 **2-3 周**")
    lines.append("\n⚠️ 考试当天突发情况，应**先电话通知辅导员**，再补交材料。")
    return "\n".join(lines)


def render_eligibility(reason: str) -> str:
    reason_desc = {
        REASON_ILLNESS: ("✅ 符合缓考条件（因病）", "请准备校医院或三甲医院的诊断证明。"),
        REASON_EMERGENCY: ("✅ 符合缓考条件（因事）", "请准备相关证明材料 + 辅导员签字情况说明。"),
        REASON_CONFLICT: ("✅ 符合缓考条件（考试冲突）", "⚠️ 必须在考试前 5 个工作日提出申请。"),
        REASON_FORCE_MAJEURE: ("✅ 符合缓考条件（不可抗力）", "请保留官方通告作为证明。"),
        REASON_UNKNOWN: ("❓ 需要更多信息判断", "请告诉我具体情况，例如：生病了 / 家里有急事 / 两门考试冲突等。"),
    }
    title, tip = reason_desc[reason]
    return f"## 缓考资格判断\n\n{title}\n\n{tip}\n\n📋 完整资格条件：\n1. **因病缓考** - 需校医院/三甲医院诊断证明\n2. **因事缓考** - 突发事件（家庭变故/事故等）\n3. **考试冲突** - 两门及以上考试时间重叠\n4. **不可抗力** - 自然灾害、公共卫生事件等\n\n⚠️ \"没复习好\"\"想多准备\"**不属于**缓考条件。"


def render_multi_exam() -> str:
    return """## 多门考试缓考指引

需要多门课程同时缓考时：

1. **每门课程单独提交一份申请** — 不能合并申请表
2. **证明材料可以复用** — 同一份诊断证明可复印多份分别附上
3. **申请表逐门填写** — 注明各自课程名称、考试时间、任课老师
4. **建议一次性提交** — 把所有申请材料一起交到学院教务办，避免遗漏
5. **逐门审核** — 学院会对每门课单独审核，结果可能不一致

📝 **建议流程**：
- 先列清单：科目 / 考试时间 / 任课老师 / 学分
- 一次性复印所需份数的证明材料
- 一次性提交，附一份汇总说明

⚠️ 如果是**考试冲突**类缓考，只能申请其中一门（通常选学分高的或重修的）。"""


def render_compare() -> str:
    return """## 缓考 / 补考 / 重修 - 对比

| 项目 | 缓考 | 补考 | 重修 |
|------|------|------|------|
| **触发条件** | 考前/考中因故无法参加 | 正常考但未通过 | 补考未过或主动选择 |
| **成绩计分** | 按正常考试计分 | 通常有上限（最高 75） | 按正常考试计分 |
| **影响绩点** | ❌ 不影响 | ⚠️ 可能受限 | ❌ 不影响 |
| **考试时间** | 下学期开学第 2-3 周 | 下学期开学第 2-3 周 | 需重新选课 |
| **是否需申请** | ✅ 需要 | ❌ 自动安排 | ✅ 需选课 |
| **额外费用** | 无 | 无 | 按学分缴费 |

💡 **结论**：如果符合缓考条件，缓考是最优选择（成绩按正常计分，不影响绩点）。"""


def render_missed() -> str:
    return """## 已错过考试怎么办

如果你已经缺考，仍然有救：

1. **3 个工作日内**联系辅导员说明情况
2. 准备**事后补交**的证明材料：
   - 因病：当天的医院就诊记录、急诊单
   - 因事：相关证明文件
3. 填写《缓考申请表》并注明\"考后补办\"
4. 由辅导员陪同到学院教务办说明
5. 学院根据情况决定是否受理

⚠️ **重要提示**：
- 超过 3 个工作日基本无法补办，按**旷考**处理，成绩 0 分
- 旷考可能影响奖学金、保研资格
- 越早联系辅导员越好，**当天就联系最佳**

📞 紧急联系：辅导员手机 → 学院教务办公室"""


def general_intro() -> str:
    return """## 缓考助手 ✨

你好！我是缓考助手 Partner Agent，可以帮你：

| 询问 | 我能回答 |
|------|---------|
| 🔍 我能申请缓考吗？ | 资格判断 |
| 📋 需要准备什么材料？ | 材料清单 |
| 📝 怎么申请？ | 完整流程 |
| ⏰ 截止日期是什么时候？ | 时间节点 |
| 📚 多门课能一起缓考吗？ | 批量处理 |
| ❓ 缓考和补考有什么区别？ | 对比说明 |
| 😱 我已经缺考了怎么办？ | 应急方案 |

请描述你的具体情况，我会给你针对性的建议！"""


def answer(query: str) -> dict:
    """统一入口：返回 {answer, intent, reason, skills}"""
    intent = detect_intent(query)
    reason = detect_reason(query)

    if intent == "eligibility":
        text = render_eligibility(reason)
        skills = ["eligibility_check"]
    elif intent == "materials":
        text = render_materials(reason if reason != REASON_UNKNOWN else REASON_ILLNESS)
        skills = ["materials_list"]
    elif intent == "steps":
        text = render_steps()
        skills = ["application_guide"]
    elif intent == "deadline":
        text = render_deadlines()
        skills = ["deadline_query"]
    elif intent == "multi":
        text = render_multi_exam()
        skills = ["multi_exam_defer"]
    elif intent == "compare":
        text = render_compare()
        skills = ["scenario_adapt"]
    elif intent == "missed":
        text = render_missed()
        skills = ["scenario_adapt"]
    else:
        # 通用：如果识别到 reason，给资格+材料组合答案
        if reason != REASON_UNKNOWN:
            text = render_eligibility(reason) + "\n\n---\n\n" + render_materials(reason)
            skills = ["eligibility_check", "materials_list"]
        else:
            text = general_intro()
            skills = ["general_query"]

    return {
        "answer": text,
        "intent": intent,
        "reason": reason,
        "skills": skills,
    }
