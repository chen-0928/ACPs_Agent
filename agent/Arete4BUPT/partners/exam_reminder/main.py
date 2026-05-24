"""
Arete4BUPT Partner Agent — 考试提醒助手 (FastAPI)
AIP v02.00 合规版：提醒支持、超时机制、状态转移修正
"""
import asyncio
import json
import logging
import os
import re
import ssl
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union, Any

import aiosqlite
import toml
import uvicorn
from fastapi import FastAPI
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from acps_sdk.aip import (
    Product,
    TaskCommand,
    TaskCommandType,
    TaskResult,
    TaskState,
    TaskStatus,
    TextDataItem,
)
from acps_sdk.aip.aip_rpc_model import RpcRequest, RpcResponse
from acps_sdk.aip.aip_rpc_server import CommandHandlers

# ---------------------------------------------------------------------------
# JSON 结构化日志
# ---------------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径与配置
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

acs_path = BASE_DIR / "acs.json"
try:
    with open(acs_path, encoding="utf-8") as f:
        acs = json.load(f)
    AGENT_AIC = acs.get("aic", "exam-reminder-partner")
except Exception:
    logger.warning("未找到 acs.json，使用默认 AIC")
    AGENT_AIC = "exam-reminder-partner"

config_path = BASE_DIR / "config.toml"
try:
    config = toml.load(config_path)
    llm_config = config["llm"]["default"]
    server_config = config["server"]
    mtls_config = server_config.get("mtls", {})
    reminder_config = config.get("reminder", {})
    DEFAULT_REMINDER_DAYS = reminder_config.get("default_reminder_days", 3)
    MIN_GAP_MINUTES = reminder_config.get("min_gap_minutes", 60)
    TASK_TIMEOUT_MINUTES = reminder_config.get("task_timeout_minutes", 30)
except Exception as e:
    logger.critical(f"读取 config.toml 失败: {e}")
    raise

API_KEY = os.getenv("LLM_API_KEY", llm_config.get("api_key"))
if not API_KEY:
    logger.critical("未找到 LLM API Key")
    raise ValueError("LLM_API_KEY 环境变量或 config.toml 中 api_key 必须设置")

prompts_path = BASE_DIR / "prompts.toml"
try:
    prompts = toml.load(prompts_path)
    decision_prompt = prompts["decision"]["system"]
    analysis_prompt = prompts["analysis"]["system"]
    production_prompt = prompts["production"]["system"]
except Exception as e:
    logger.critical(f"读取 prompts.toml 失败: {e}")
    raise

# ---------------------------------------------------------------------------
# LLM 客户端（带超时）
# ---------------------------------------------------------------------------
import httpx

from footprint_sdk import report_call

llm_client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=llm_config["base_url"],
    timeout=httpx.Timeout(30.0, connect=10.0),
)

# ---------------------------------------------------------------------------
# 持久化数据库
# ---------------------------------------------------------------------------
DB_PATH = BASE_DIR / "task_store.db"

tasks: Dict[str, TaskResult] = {}
task_inputs: Dict[str, List[str]] = {}
task_timers: Dict[str, asyncio.Task] = {}  # 超时定时器
db_lock = asyncio.Lock()


async def init_db():
    async with aiosqlite.connect(str(DB_PATH), timeout=10) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                state TEXT NOT NULL,
                result_json TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at)")
        await db.commit()
    logger.info("数据库初始化完成")


async def load_active_tasks():
    async with aiosqlite.connect(str(DB_PATH), timeout=10) as db:
        cursor = await db.execute(
            "SELECT task_id, session_id, state, result_json, inputs_json FROM tasks "
            "WHERE state NOT IN ('completed','failed','canceled','rejected')"
        )
        rows = await cursor.fetchall()
        for row in rows:
            task_id, session_id, state, result_json, inputs_json = row
            try:
                result = TaskResult.model_validate_json(result_json)
                tasks[task_id] = result
                inputs = json.loads(inputs_json)
                task_inputs[task_id] = inputs
                logger.info(f"恢复任务: {task_id} (state={state})")
                if state in ('accepted', 'working'):
                    asyncio.create_task(execute_task_lifecycle(task_id))
                # 重新设置超时计时器（如果任务处于等待状态）
                if state in ('awaiting-input', 'awaiting-completion'):
                    start_timeout_timer(task_id)
            except Exception as e:
                logger.warning(f"恢复任务 {task_id} 失败: {e}")
    logger.info(f"已恢复 {len(tasks)} 个活跃任务")


async def save_task(task_id: str):
    result = tasks.get(task_id)
    if not result:
        return
    inputs = task_inputs.get(task_id, [])
    async with db_lock:
        async with aiosqlite.connect(str(DB_PATH), timeout=10) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO tasks 
                (task_id, session_id, state, result_json, inputs_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    result.sessionId,
                    result.status.state.value,
                    result.model_dump_json(),
                    json.dumps(inputs, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()


async def delete_task_from_db(task_id: str):
    async with db_lock:
        async with aiosqlite.connect(str(DB_PATH), timeout=10) as db:
            await db.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            await db.commit()


async def cleanup_old_tasks():
    while True:
        await asyncio.sleep(86400)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        async with db_lock:
            async with aiosqlite.connect(str(DB_PATH), timeout=10) as db:
                await db.execute(
                    "DELETE FROM tasks WHERE state IN ('completed','failed','canceled','rejected') "
                    "AND updated_at < ?",
                    (cutoff,)
                )
                await db.commit()
        logger.info("已清理过期终态任务")


# ---------------------------------------------------------------------------
# 上下文清理
# ---------------------------------------------------------------------------
TERMINAL_STATES = {
    TaskState.Completed,
    TaskState.Failed,
    TaskState.Canceled,
    TaskState.Rejected,
}


def cleanup_context(task_id: str):
    if task_id in task_inputs:
        del task_inputs[task_id]
    # 取消超时定时器
    if task_id in task_timers:
        task_timers[task_id].cancel()
        del task_timers[task_id]


# ---------------------------------------------------------------------------
# 输入安全
# ---------------------------------------------------------------------------
MAX_INPUT_LENGTH = 2000


def sanitize_user_input(text: str) -> str:
    if len(text) > MAX_INPUT_LENGTH:
        raise ValueError(f"输入过长，最大允许 {MAX_INPUT_LENGTH} 字符")
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<user_input>\n{safe}\n</user_input>"


# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((Exception,)),
    reraise=True,
)
async def call_llm(prompt_system: str, prompt_user: str) -> str:
    logger.info("LLM 调用开始")
    response = await llm_client.chat.completions.create(
        model=llm_config["model"],
        messages=[
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": prompt_user},
        ],
        temperature=0.3,
    )
    logger.info("LLM 调用成功")
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# 超时机制
# ---------------------------------------------------------------------------
async def timeout_task(task_id: str):
    """等待超时后自动取消任务"""
    await asyncio.sleep(TASK_TIMEOUT_MINUTES * 60)
    task = tasks.get(task_id)
    if task and task.status.state in (TaskState.AwaitingInput, TaskState.AwaitingCompletion):
        logger.info(f"任务 {task_id} 超时，自动取消")
        task.status = TaskStatus(
            state=TaskState.Canceled,
            stateChangedAt=datetime.now(timezone.utc).isoformat(),
            dataItems=[TextDataItem(text="任务超时，自动取消")]
        )
        await save_task(task_id)
        cleanup_context(task_id)


def start_timeout_timer(task_id: str):
    """为等待状态的任务启动超时计时器"""
    if task_id in task_timers:
        task_timers[task_id].cancel()
    task_timers[task_id] = asyncio.create_task(timeout_task(task_id))


def cancel_timeout_timer(task_id: str):
    if task_id in task_timers:
        task_timers[task_id].cancel()
        del task_timers[task_id]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def create_task_result(
    command: TaskCommand,
    state: TaskState,
    products: Optional[List[Product]] = None,
    message: Optional[str] = None,
    questions: Optional[List[str]] = None,
) -> TaskResult:
    data_items = []
    if message:
        data_items.append(TextDataItem(text=message))
    if questions:
        data_items.extend([TextDataItem(text=q) for q in questions])

    return TaskResult(
        id=f"msg-{uuid.uuid4()}",
        sentAt=datetime.now(timezone.utc).isoformat(),
        senderRole="partner",
        senderId=AGENT_AIC,
        taskId=command.taskId,
        status=TaskStatus(
            state=state,
            stateChangedAt=datetime.now(timezone.utc).isoformat(),
            dataItems=data_items if data_items else None,
        ),
        products=products,
        sessionId=command.sessionId,
    )


async def process_decision(user_input: str) -> bool:
    safe_input = sanitize_user_input(user_input)
    response = await call_llm(
        decision_prompt,
        f"请求内容：{safe_input}\n请判断是否接受此任务。",
    )
    try:
        result = json.loads(response)
        return result.get("accepted", False)
    except json.JSONDecodeError:
        logger.error(f"决策阶段解析失败: {response}")
        return False


def build_analysis_input(task_id: str, new_input: str) -> str:
    history = task_inputs.get(task_id, [])
    lines = [f"用户消息 {i+1}: {h}" for i, h in enumerate(history)]
    combined = "\n".join(lines)
    if combined:
        combined += f"\n用户最新消息: {new_input}"
    else:
        combined = new_input
    return combined


def sanitize_time_range(tr: Any) -> Optional[List[str]]:
    if not tr:
        return None
    if isinstance(tr, str):
        tr = tr.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", tr):
            return [tr, tr]
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*[到至\-～~,，]+\s*(\d{4}-\d{2}-\d{2})", tr)
        if m:
            d1, d2 = m.group(1), m.group(2)
            return [d1, d2] if d1 <= d2 else [d2, d1]
        return None
    if isinstance(tr, list):
        if len(tr) == 1 and isinstance(tr[0], str) and re.match(r"^\d{4}-\d{2}-\d{2}$", tr[0]):
            return [tr[0], tr[0]]
        if len(tr) == 2 and all(isinstance(d, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", d) for d in tr):
            return [tr[0], tr[1]] if tr[0] <= tr[1] else [tr[1], tr[0]]
    return None


async def process_analysis(task_id: str, new_input: str) -> dict:
    today = date.today().strftime("%Y年%m月%d日")
    prompt_with_date = analysis_prompt.replace("{{ current_date }}", today)
    full_input = build_analysis_input(task_id, new_input)
    safe_input = sanitize_user_input(full_input)
    response = await call_llm(
        prompt_with_date,
        f"学生请求历史与最新内容：{safe_input}\n请分析。",
    )
    try:
        result = json.loads(response)
        result.setdefault("is_ready", False)
        result.setdefault("params", {})
        result.setdefault("questions", [])

        raw_tr = result["params"].get("time_range")
        formatted = sanitize_time_range(raw_tr)

        if raw_tr and not formatted:
            result["is_ready"] = False
            result["params"]["time_range"] = None
            result["questions"] = ["请提供有效的考试日期范围（例如 2026-06-15 或 2026-06-01 至 2026-06-30）"]
        else:
            result["params"]["time_range"] = formatted
            if formatted and not result["is_ready"]:
                result["is_ready"] = True

        return result
    except json.JSONDecodeError:
        logger.error(f"分析阶段解析失败: {response}")
        return {
            "is_ready": False,
            "params": {},
            "questions": ["抱歉，我没理解您的需求，请详细说明要查询的考试信息"],
        }


# ---------------------------------------------------------------------------
# 考试数据与冲突检测
# ---------------------------------------------------------------------------
EXAM_DATA_PATH = BASE_DIR / "exam_data.json"


def load_exam_data():
    if not EXAM_DATA_PATH.exists():
        logger.warning("考试数据文件 exam_data.json 不存在")
        return {"exams": []}
    with open(EXAM_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def query_exams(course_names=None, time_range=None):
    data = load_exam_data()
    exams = data.get("exams", [])

    if course_names and "所有课程" not in course_names:
        exact_matches = []
        fuzzy_matches = []
        for e in exams:
            for c in course_names:
                if e["course_name"] == c:
                    exact_matches.append(e)
                    break
                elif c in e["course_name"]:
                    fuzzy_matches.append(e)
                    break
        seen_ids = set()
        filtered = []
        for e in exact_matches + fuzzy_matches:
            eid = e["course_name"] + e["exam_date"] + e["start_time"]
            if eid not in seen_ids:
                seen_ids.add(eid)
                filtered.append(e)
        exams = filtered

    if time_range and len(time_range) == 2:
        start_str, end_str = time_range
        exams = [e for e in exams if start_str <= e["exam_date"] <= end_str]

    return exams


def detect_conflicts(exams, min_gap_minutes=60):
    conflicts = []
    tight_gaps = []
    # 将内嵌函数移到外部以提高性能
    def to_minutes(exam):
        h, m = map(int, exam["start_time"].split(":"))
        return h * 60 + m
    def to_end_minutes(exam):
        h, m = map(int, exam["end_time"].split(":"))
        return h * 60 + m

    for i in range(len(exams)):
        for j in range(i + 1, len(exams)):
            e1, e2 = exams[i], exams[j]
            if e1["exam_date"] != e2["exam_date"]:
                continue

            start1, end1 = to_minutes(e1), to_end_minutes(e1)
            start2, end2 = to_minutes(e2), to_end_minutes(e2)

            if not (end1 <= start2 or end2 <= start1):
                conflicts.append((e1, e2))
            else:
                gap = start2 - end1 if end1 <= start2 else start1 - end2
                if gap < min_gap_minutes:
                    tight_gaps.append((e1, e2, gap))
    return conflicts, tight_gaps


def generate_ical(exams):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Arete4BUPT//Exam Calendar//CN"]
    for e in exams:
        dt_start = f"{e['exam_date'].replace('-','')}T{e['start_time'].replace(':','')}00"
        dt_end = f"{e['exam_date'].replace('-','')}T{e['end_time'].replace(':','')}00"
        lines.append("BEGIN:VEVENT")
        lines.append(f"DTSTART:{dt_start}")
        lines.append(f"DTEND:{dt_end}")
        lines.append(f"SUMMARY:{e['course_name']} 考试")
        lines.append(f"LOCATION:{e['location']} 座位 {e['seat']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\n".join(lines)


def generate_csv(exams):
    header = "课程,日期,开始时间,结束时间,地点,座位"
    rows = [header]
    for e in exams:
        rows.append(f"{e['course_name']},{e['exam_date']},{e['start_time']},{e['end_time']},{e['location']},{e['seat']}")
    return "\n".join(rows)


def build_reminder_messages(reminder_days: Union[int, List[int]], course_filter: str = None) -> List[str]:
    if isinstance(reminder_days, int):
        reminder_days = [reminder_days]
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    messages = []
    exams = load_exam_data().get("exams", [])
    for e in exams:
        exam_date = e["exam_date"]
        if exam_date < today_str:
            continue
        if course_filter and course_filter not in e["course_name"]:
            continue
        days_left = (datetime.strptime(exam_date, "%Y-%m-%d") - now).days
        if days_left in reminder_days or days_left == 1 or days_left == 0:
            msg = f"🔔 {e['course_name']} 考试将在 {days_left} 天后（{exam_date} {e['start_time']}-{e['end_time']}）于 {e['location']} 座位 {e['seat']} 进行。"
            messages.append(msg)
    return messages


async def process_production(params: dict) -> str:
    export_calendar = params.get("export_calendar", False)
    export_format = params.get("export_format", "ical")
    is_reminder = params.get("is_reminder", False)
    course_names = params.get("course_names", ["所有课程"])
    time_range = params.get("time_range")
    reminder_days = params.get("reminder_days", DEFAULT_REMINDER_DAYS)
    need_detect = params.get("need_conflict_detection", True)
    min_gap = params.get("min_gap_minutes", MIN_GAP_MINUTES)

    exams = query_exams(course_names, time_range)
    if not exams:
        if is_reminder:
            return "未来一段时间内没有需要关注的考试，放松一下吧！"
        return f"在指定条件（课程: {course_names}, 时间: {time_range}）下未找到考试安排。"

    # 如果是纯粹的提醒查询，直接生成简洁的提醒列表
    if is_reminder:
        msgs = build_reminder_messages(reminder_days)
        if not msgs:
            return "未来一段时间内没有需要关注的考试。"
        return "📌 **近期考试提醒**\n" + "\n".join(msgs)

    if export_calendar:
        if export_format == "csv":
            content = generate_csv(exams)
            return f"请将以下内容保存为 .csv 文件：\n{content}"
        else:
            ical = generate_ical(exams)
            return f"请将以下内容保存为 .ics 文件并导入日历：\n{ical}"

    conflicts, tight_gaps = [], []
    if need_detect:
        conflicts, tight_gaps = detect_conflicts(exams, min_gap)

    data_context = {
        "exams": exams,
        "conflicts": [{"exam1": c[0], "exam2": c[1]} for c in conflicts],
        "tight_gaps": [{"exam1": g[0], "exam2": g[1], "gap_minutes": g[2]} for g in tight_gaps],
        "reminder_days": reminder_days,
        "need_conflict_detection": need_detect,
    }
    safe_context = sanitize_user_input(json.dumps(data_context, ensure_ascii=False, indent=2))
    return await call_llm(
        production_prompt,
        f"以下是查询到的真实考试数据：\n{safe_context}\n请根据这些数据生成考试日程与提醒。注意区分时间冲突（重叠）和间隔紧张（小于{min_gap}分钟）。"
    )


# ---------------------------------------------------------------------------
# 后台任务生命周期
# ---------------------------------------------------------------------------
async def execute_task_lifecycle(task_id: str):
    try:
        task = tasks.get(task_id)
        if not task:
            return
        # 确保进入 Working 状态
        task.status = TaskStatus(
            state=TaskState.Working,
            stateChangedAt=datetime.now(timezone.utc).isoformat(),
            dataItems=task.status.dataItems,
        )
        await save_task(task_id)

        user_inputs = task_inputs.get(task_id, [])
        if not user_inputs:
            raise ValueError("缺少用户输入")
        analysis = await process_analysis(task_id, user_inputs[-1])

        if not analysis["is_ready"]:
            task.status = TaskStatus(
                state=TaskState.AwaitingInput,
                stateChangedAt=datetime.now(timezone.utc).isoformat(),
                dataItems=[TextDataItem(text=q) for q in analysis["questions"]],
            )
            start_timeout_timer(task_id)  # 启动超时
        else:
            output = await process_production(analysis["params"])
            product = Product(
                id=f"product-{uuid.uuid4()}",
                name="exam_reminder_result",
                dataItems=[TextDataItem(text=output)],
            )
            task.status = TaskStatus(
                state=TaskState.AwaitingCompletion,
                stateChangedAt=datetime.now(timezone.utc).isoformat(),
                dataItems=None,
            )
            task.products = [product]
            start_timeout_timer(task_id)  # 启动超时

        await save_task(task_id)

    except Exception as e:
        logger.error(f"任务 {task_id} 执行失败: {e}", exc_info=True)
        if task_id in tasks:
            tasks[task_id].status = TaskStatus(
                state=TaskState.Failed,
                stateChangedAt=datetime.now(timezone.utc).isoformat(),
                dataItems=[TextDataItem(text=f"处理失败: {str(e)}")],
            )
            await save_task(task_id)
        cleanup_context(task_id)


# ---------------------------------------------------------------------------
# 命令处理器
# ---------------------------------------------------------------------------
async def on_start(command: TaskCommand, task: Optional[TaskResult]) -> TaskResult:
    # 如果 taskId 已存在（无论状态），忽略重复 Start
    if command.taskId and command.taskId in tasks:
        existing = tasks[command.taskId]
        logger.info(f"任务 {command.taskId} 已存在，忽略重复 Start")
        return existing

    user_input = command.dataItems[0].text if command.dataItems else ""

    try:
        sanitize_user_input(user_input)
    except ValueError as e:
        result = create_task_result(command, TaskState.Rejected, message=str(e))
        tasks[command.taskId] = result
        await save_task(command.taskId)
        cleanup_context(command.taskId)
        return result

    task_inputs[command.taskId] = [user_input]

    accepted = await process_decision(user_input)
    if not accepted:
        result = create_task_result(
            command, TaskState.Rejected, message="请求不符合考试提醒服务范围"
        )
        tasks[command.taskId] = result
        await save_task(command.taskId)
        cleanup_context(command.taskId)
        return result

    result = create_task_result(command, TaskState.Accepted)
    tasks[command.taskId] = result
    await save_task(command.taskId)
    asyncio.create_task(execute_task_lifecycle(command.taskId))
    return result


async def on_continue(command: TaskCommand, task: TaskResult) -> TaskResult:
    if task is None or task.status.state not in (TaskState.AwaitingInput, TaskState.AwaitingCompletion):
        logger.warning(f"忽略 Continue，任务 {command.taskId} 状态 {task.status.state if task else 'None'}")
        return task

    new_input = command.dataItems[0].text if command.dataItems else ""
    try:
        sanitize_user_input(new_input)
    except ValueError as e:
        result = create_task_result(command, TaskState.Failed, message=str(e))
        tasks[command.taskId] = result
        await save_task(command.taskId)
        cleanup_context(command.taskId)
        return result

    task_inputs.setdefault(command.taskId, []).append(new_input)
    await save_task(command.taskId)

    # 返回 Working 状态，后台异步执行
    working_result = create_task_result(command, TaskState.Working)
    working_result.taskId = command.taskId
    working_result.sessionId = task.sessionId
    tasks[command.taskId] = working_result
    await save_task(command.taskId)

    asyncio.create_task(execute_task_lifecycle(command.taskId))
    return working_result


async def on_complete(command: TaskCommand, task: TaskResult) -> TaskResult:
    if task and task.status.state == TaskState.AwaitingCompletion:
        task.status = TaskStatus(
            state=TaskState.Completed,
            stateChangedAt=datetime.now(timezone.utc).isoformat(),
            dataItems=task.status.dataItems,
        )
        tasks[command.taskId] = task
        await save_task(command.taskId)
        cleanup_context(command.taskId)
    return task


async def on_cancel(command: TaskCommand, task: TaskResult) -> TaskResult:
    if task and task.status.state not in TERMINAL_STATES:
        task.status = TaskStatus(
            state=TaskState.Canceled,
            stateChangedAt=datetime.now(timezone.utc).isoformat(),
            dataItems=task.status.dataItems,
        )
        tasks[command.taskId] = task
        await save_task(command.taskId)
        cleanup_context(command.taskId)
    return task


async def on_get(command: TaskCommand, task: TaskResult) -> TaskResult:
    return task


handlers = CommandHandlers(
    on_start=on_start,
    on_continue=on_continue,
    on_complete=on_complete,
    on_cancel=on_cancel,
    on_get=on_get,
)


# ---------------------------------------------------------------------------
# 应用生命周期
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await load_active_tasks()
    asyncio.create_task(cleanup_old_tasks())
    yield


# ---------------------------------------------------------------------------
# FastAPI 应用实例
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Arete4BUPT 考试提醒助手",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# RPC 端点
# ---------------------------------------------------------------------------
@app.post("/rpc", response_model=RpcResponse)
async def handle_rpc(request: RpcRequest) -> RpcResponse:
    command = request.params.command

    # ★ 协作前上报 Footprint
    await report_call("个人课程助手Leader",
                      "1.2.156.3088.0001.00001.R1JUQE.821HRL.1.0YVV",
                      "考试提醒助手", AGENT_AIC)

    try:
        existing_task = tasks.get(command.taskId)

        if command.command == TaskCommandType.Start:
            result = await handlers.on_start(command, existing_task)
        elif command.command == TaskCommandType.Continue:
            result = await handlers.on_continue(command, existing_task)
        elif command.command == TaskCommandType.Complete:
            result = await handlers.on_complete(command, existing_task)
        elif command.command == TaskCommandType.Cancel:
            result = await handlers.on_cancel(command, existing_task)
        elif command.command == TaskCommandType.Get:
            result = await handlers.on_get(command, existing_task)
        else:
            logger.warning(f"不支持的命令: {command.command}")
            result = None

        if result is not None:
            tasks[command.taskId] = result
        return RpcResponse(id=request.id, result=result)

    except Exception as e:
        logger.error(f"处理命令 {command.command} 时出错: {str(e)}", exc_info=True)
        error_result = create_task_result(
            command,
            TaskState.Failed,
            message=f"处理失败: {str(e)}",
        )
        tasks[command.taskId] = error_result
        await save_task(command.taskId)
        cleanup_context(command.taskId)
        return RpcResponse(id=request.id, result=error_result)


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    db_ok = False
    try:
        async with aiosqlite.connect(str(DB_PATH), timeout=5) as db:
            await db.execute("SELECT 1")
        db_ok = True
    except Exception as e:
        logger.error(f"数据库健康检查失败: {e}")

    llm_ok = False
    try:
        await llm_client.models.list()
        llm_ok = True
    except Exception as e:
        logger.error(f"LLM 健康检查失败: {e}")

    return {
        "status": "ok" if (db_ok and llm_ok) else "degraded",
        "database": db_ok,
        "llm": llm_ok,
    }


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cert_file = None
    key_file = None
    ca_file = None

    if mtls_config.get("tls_enabled", False):
        cert_file = BASE_DIR / mtls_config.get("cert_file", "certs/server.crt")
        key_file = BASE_DIR / mtls_config.get("key_file", "certs/server.key")
        ca_file = BASE_DIR / mtls_config.get("ca_file", "certs/ca.crt")

        if not cert_file.exists() or not key_file.exists():
            logger.error("mTLS 已启用但证书文件缺失")
            raise FileNotFoundError("证书文件缺失")
        logger.info("已启用 TLS，证书加载完毕")
    else:
        logger.info("TLS 已禁用，服务将运行在 HTTP 模式")

    uvicorn.run(
        "main:app",
        host=server_config.get("host", "0.0.0.0"),
        port=server_config.get("port", 59224),
        ssl_certfile=str(cert_file) if cert_file else None,
        ssl_keyfile=str(key_file) if key_file else None,
        ssl_ca_certs=str(ca_file) if ca_file else None,
        reload=False,
    )