"""主编排器 —— 5 阶段串联: 意图→发现→拆解→执行→整合.

orchestrate() 作为 fire-and-forget 后台任务运行，通过 task.stage 和 task.status
对外暴露实时进度，前端通过 GET /api/v1/result/{session_id} 轮询。
"""

import asyncio
import json
import logging
from typing import Optional

from .session import Session, Task, TaskStatus, get_session_manager
from .llm_client import chat, chat_json
from .aip_client import call_partner
from .discovery import discover_agents

logger = logging.getLogger(__name__)

# Partner 能力描述（静态 catalog，供 LLM prompt 用）
PARTNER_CATALOG = {
    "选课助手": {
        "name": "选课助手",
        "description": "课程查询、方向推荐、先修检查、容量查询、选课方向规划。仅处理校内选课相关。",
        "reject": "校外课程、考研选导、请假/考试提醒/缓考",
        "aic": "1.2.156.3088.0001.00001.T1DSWF.UEFEWI.1.0Z6R",
    },
    "请假助手": {
        "name": "请假助手",
        "description": "请假申请生成、审批流程指引、材料清单、病假/事假/公假区分。仅处理校内课程请假。",
        "reject": "校外请假、社团请假、选课/考试提醒/缓考",
        "aic": "1.2.156.3088.0001.00001.HBQ3SF.F7JHGG.1.07HK",
    },
    "考试提醒助手": {
        "name": "考试提醒助手",
        "description": "考试时间查询、冲突检测、考前DDL提醒、考场信息推送。仅处理校内考试。",
        "reject": "非考试日程、补考/重修、选课/请假/缓考",
        "aic": "1.2.156.3088.0001.00001.E3GP7C.E6A4I1.1.0HJ7",
    },
    "缓考助手": {
        "name": "缓考助手",
        "description": "缓考资格判断、材料清单、申请步骤指引、截止日期说明。仅处理校内课程缓考。",
        "reject": "补考/重修安排、免修申请、选课/请假/考试提醒",
        "aic": "1.2.156.3088.0001.00001.6CMY1O.ZTFJB0.1.0HE0",
    },
}

CATALOG_TEXT = "\n".join(
    f"- {p['name']}: {p['description']} （拒绝: {p['reject']}）"
    for p in PARTNER_CATALOG.values()
)


# ═════════════════ 阶段1: 意图分析 ═════════════════

INTENT_SYSTEM = """你是北京邮电大学的学生个人课程助手。你需要分析学生的请求，判断意图类型。

你可以调度的 Partner 智能体如下：
""" + CATALOG_TEXT + """

请输出 JSON：
{
  "intent_type": "选课 / 请假 / 缓考 / 考试提醒 / 混合 / 外部",
  "confidence": 0.0-1.0,
  "extracted_info": {
    "scenario": "具体场景关键词",
    "urgency": "normal / urgent",
    "keywords": ["关键", "词"]
  },
  "needs_clarification": false,
  "clarification_question": "如果需要追问，写追问内容"
}

注意：如果学生请求完全不属于选课/请假/缓考/考试提醒的范围（如科研、生活、社团等），intent_type 填 "外部"，needs_clarification 填 false（交由 ADP 发现的外部 Agent 处理）。"""


async def analyze_intent(user_message: str) -> dict:
    """阶段1: 分析用户意图."""
    logger.info("[1/5] 意图分析中...")
    result = chat_json(
        system_prompt=INTENT_SYSTEM,
        user_message=f"学生提问：{user_message}",
        profile="fast",
    )
    logger.info("[1/5] 意图: type=%s confidence=%.2f",
                result.get("intent_type"), result.get("confidence", 0))
    return result


# ═════════════════ 阶段2: ADP 动态发现 ═════════════════

async def discover_partners(intent: dict, user_message: str) -> dict:
    """阶段2: 从 ADP 服务器发现可用的 Partner，获取真实 endPoints.
    返回: {"internal": {cat_name: info}, "external": [{agent_info}, ...]}"""
    logger.info("[2/5] ADP 发现中...")
    intent_type = intent.get("intent_type", "选课")
    keywords = intent.get("extracted_info", {}).get("keywords", [])
    search_query = f"{intent_type} {' '.join(keywords)}" if keywords else intent_type

    agents = await discover_agents(search_query)

    internal: dict[str, dict] = {}
    external: list[dict] = []

    for ag in agents:
        name = ag["name"]
        matched = None
        for cat_name in PARTNER_CATALOG:
            if cat_name in name or name in cat_name:
                matched = cat_name
                break
        if matched:
            internal[matched] = {
                "aic": ag["aic"],
                "endpoint": ag["endpoint"],
                "name": name,
                "skills": ag["skills"],
            }
        else:
            external.append({
                "aic": ag.get("aic", ""),
                "endpoint": ag.get("endpoint", ""),
                "name": name,
                "description": ag.get("description", ""),
                "skills": ag.get("skills", []),
            })

    logger.info("[2/5] ADP 发现: %d agents → 内部=%s, 外部=%s",
                len(agents), list(internal.keys()),
                [e["name"] for e in external])
    return {"internal": internal, "external": external}


# ═════════════════ 阶段3: 任务拆解 ═════════════════

PLAN_SYSTEM_BASE = """你是任务规划专家。根据意图分析结果，将学生需求拆解为 1-4 个子任务，每个子任务对应一个 Partner。

可用的 Partner（严格遵循，不要编造）："""

PLAN_SYSTEM_TAIL = """
请输出 JSON：
{
  "subtasks": [
    {
      "partner_name": "Partner 名称（必须是上面列表中出现的名称）",
      "task_description": "用自然语言描述这个子任务，供 Partner 理解",
      "priority": 1-3,
      "depends_on": null 或 前置子任务的 partner_name
    }
  ]
}

要求：
- 每个子任务的 task_description 要具体、可执行，Partner 能直接理解
- 如果一个 Partner 足够处理，返回一个子任务即可
- 混合请求才需要拆到多个 Partner
- priority: 1最高，3最低
- depends_on: 如果有依赖关系填前置 partner_name，没有填 null"""


def _build_plan_system(external_agents: list[dict]) -> str:
    """根据发现的内部+外部 Agent 构建规划 prompt."""
    parts = [PLAN_SYSTEM_BASE]
    # 内部 Partner
    parts.append("\n【本组 Partner】")
    parts.append(CATALOG_TEXT)
    # 外部 Agent（ADP 发现的其他组）
    if external_agents:
        parts.append("\n【跨组可调用 Agent（ADP 发现）】")
        for ag in external_agents:
            skills_text = ", ".join(ag.get("skills", [])) or "通用"
            desc = ag.get("description", "")[:120]
            parts.append(f"- {ag['name']}: {desc}（技能: {skills_text}）")
    parts.append(PLAN_SYSTEM_TAIL)
    return "\n".join(parts)


async def plan_subtasks(intent: dict, user_message: str,
                        external_agents: list[dict] = None) -> list[dict]:
    """阶段3: 拆解为子任务."""
    logger.info("[3/5] 任务拆解中...")
    plan_system = _build_plan_system(external_agents or [])
    result = chat_json(
        system_prompt=plan_system,
        user_message=f"原始需求：{user_message}\n意图分析：{json.dumps(intent, ensure_ascii=False)}",
        profile="default",
        max_tokens=3072,
    )
    subtasks = result.get("subtasks", [])
    logger.info("[3/5] 拆解出 %d 个子任务: %s",
                len(subtasks), [s.get("partner_name") for s in subtasks])
    return subtasks


# ═════════════════ 阶段4: 执行 ═════════════════


async def execute_subtasks(
    session_id: str,
    task: Task,
    subtasks: list[dict],
    endpoints: dict[str, str],
) -> list[dict]:
    """阶段4: 依次调用 Partner（使用 ADP 发现的 endPoints），处理依赖关系."""
    logger.info("[4/5] 开始执行 %d 个子任务...", len(subtasks))
    results = []
    done: dict[str, dict] = {}

    for st in subtasks:
        partner = st["partner_name"]
        is_external = partner not in PARTNER_CATALOG

        dep = st.get("depends_on")
        dep_result = None
        if dep and dep in done:
            dep_result = done[dep]

        payload = {
            "message": st["task_description"],
            "original_message": task.results[0].get("intent", {}).get("extracted_info", {}) if task.results else {},
            "depends_on_result": dep_result,
        }

        task.status = TaskStatus.RUNNING
        endpoint = endpoints.get(partner)
        result = await call_partner(partner, task.id, payload,
                                    endpoint=endpoint, external=is_external)
        done[partner] = result
        results.append({
            "partner": partner,
            "subtask": st["task_description"],
            "result": result,
        })
        logger.info("[4/5] %s → status=%s", partner, result.get("status", "?"))

    task.results = results
    return results


# ═════════════════ 阶段5: 结果整合 ═════════════════

AGGREGATE_SYSTEM = """你是结果整合专家。你收到了多个 Partner 智能体返回的结果，需要整合成一段自然、完整、对学生有帮助的回复。

规则：
- 如果只有一个 Partner 的结果，浓缩提炼后回复
- 如果有多个 Partner 的结果，按逻辑顺序组织，分段回复
- 如果某个 Partner 返回了错误或拒绝，礼貌地说明原因并建议替代方案
- 不要编造 Partner 没有返回的内容
- 回复语气：温暖、专业的北邮学长风格"""


async def aggregate(session: Session, task: Task, user_message: str) -> str:
    """阶段5: 整合结果."""
    logger.info("[5/5] 结果整合中...")
    results_text = json.dumps([
        {"partner": r["partner"], "subtask": r.get("subtask", ""), "result": r.get("result", {})}
        for r in task.results
    ], ensure_ascii=False, indent=2)

    answer = chat(
        system_prompt=AGGREGATE_SYSTEM,
        user_message=f"原始需求：{user_message}\n\nPartner 返回结果：\n{results_text}",
        profile="pro",
        max_tokens=4096,
    )
    logger.info("[5/5] 整合完成，长度 %d 字", len(answer))
    return answer


# ═════════════════ 主编排入口 ═════════════════

async def orchestrate(session_id: Optional[str], user_message: str, task_id: str = None):
    """5 阶段编排（后台 fire-and-forget）。阶段进度写入 task.stage 供前端轮询。
    task_id 由调用方预先创建（避免竞态），如果未提供则内部创建。"""
    sm = get_session_manager()
    session = sm.get_or_create(session_id)

    if task_id and task_id in session.tasks:
        task = session.tasks[task_id]
    else:
        task = session.create_task()
        session.history.append({"role": "user", "content": user_message})
        task.status = TaskStatus.RUNNING

    # 硬编码回退地址（ADP 不可用时使用）
    fallback_endpoints = {
        "选课助手":     "http://localhost:59221/rpc",
        "请假助手":     "http://localhost:59222/rpc",
        "缓考助手":     "http://localhost:59223/rpc",
        "考试提醒助手": "http://localhost:59224/rpc",
    }

    try:
        # 1. 意图分析
        task.stage = "intent"
        intent = await analyze_intent(user_message)
        task.results.append({"intent": intent})

        # 2. ADP 动态发现（始终执行，跨组场景需要外部 Agent）
        task.stage = "discovery"
        discovered = await discover_partners(intent, user_message)
        task.results.append({"discovery": discovered})

        # 如果意图不明确且没有发现外部 Agent 可用，才追问
        external_agents = discovered.get("external", [])
        if intent.get("needs_clarification") and not external_agents:
            task.status = TaskStatus.AWAITING_INPUT
            task.clarification = intent.get("clarification_question", "能再详细说下吗？")
            return

        # 构建 endPoints 映射（ADP 发现优先，硬编码兜底）
        endpoints: dict[str, str] = {}
        for cat_name in PARTNER_CATALOG:
            internal = discovered.get("internal", {})
            ep = (internal.get(cat_name, {}).get("endpoint", "") or "").strip()
            if cat_name in internal and ep:
                endpoints[cat_name] = ep
            else:
                endpoints[cat_name] = fallback_endpoints.get(cat_name, "")
        # 外部 Agent 的 endpoint 直接加入
        for ext in discovered.get("external", []):
            ep = (ext.get("endpoint") or "").strip()
            if ep:
                endpoints[ext["name"]] = ep
        task.endpoints = endpoints

        # 3. 任务拆解
        task.stage = "planning"
        external_agents = discovered.get("external", [])
        subtasks = await plan_subtasks(intent, user_message, external_agents)
        task.subtasks = subtasks

        # 4. 执行
        task.stage = "executing"
        await execute_subtasks(session.id, task, subtasks, endpoints)

        # 5. 整合
        task.stage = "aggregating"
        answer = await aggregate(session, task, user_message)
        task.final_answer = answer
        task.status = TaskStatus.COMPLETED
        task.stage = "completed"
        session.history.append({"role": "assistant", "content": answer})

    except Exception as e:
        logger.exception("编排失败")
        task.status = TaskStatus.FAILED
        task.stage = "failed"
        task.final_answer = f"抱歉，处理请求时出现错误：{e}"

