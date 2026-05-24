from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import toml
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from .footprint_client import get_footprint_url, notify_call
    from .leave_engine import analyze_leave_request, generate_draft
    from .schemas import LeaveAnalyzeRequest, LeaveDraftRequest, TaskCommand, TaskResult
except ImportError:  # Allows: cd partners/leave_request && uvicorn main:app
    from footprint_client import get_footprint_url, notify_call
    from leave_engine import analyze_leave_request, generate_draft
    from schemas import LeaveAnalyzeRequest, LeaveDraftRequest, TaskCommand, TaskResult


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.toml"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.toml"
ACS_PATH = BASE_DIR / "acs.json"

ALLOWED_COLLEGES = [
    "信息与通信工程学院",
    "电子工程学院",
    "人文学院",
    "国际学院",
    "网络教育学院",
    "继续教育学院",
    "马克思主义学院",
    "体育部",
    "现代邮政学院",
    "计算机学院",
    "数字媒体与设计艺术学院",
    "理学院",
    "经济管理学院",
    "公共管理学院",
    "网络空间安全学院",
    "卓越工程师学院",
    "数学科学学院",
    "物理科学与技术学院",
]

load_dotenv(BASE_DIR / ".env")


def load_config() -> Dict[str, Any]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    config: Dict[str, Any] = toml.load(path) if path.exists() else {}
    agent = config.setdefault("agent", {})
    acps = config.setdefault("acps", {})

    env_map = {
        "LEAVE_AGENT_NAME": ("agent", "name"),
        "LEAVE_AGENT_CODE": ("agent", "code"),
        "LEAVE_AGENT_ROLE": ("agent", "role"),
        "LEAVE_AGENT_AIC": ("agent", "aic"),
        "LEAVE_AGENT_VERSION": ("agent", "version"),
        "LEAVE_AGENT_FOOTPRINT_URL": ("acps", "footprint_url"),
        "FOOTPRINT_URL": ("acps", "footprint_url"),
    }
    for env_name, (section, key) in env_map.items():
        value = os.getenv(env_name)
        if value:
            config.setdefault(section, {})[key] = value

    agent.setdefault("name", "校园请假助手")
    agent.setdefault("code", "leave_request_agent")
    agent.setdefault("role", "partner")
    agent.setdefault("aic", "PLEASE_REPLACE_WITH_REAL_AIC")
    agent.setdefault("version", "0.1.0")
    agent.setdefault("local_demo_mode", True)
    acps.setdefault("footprint_url", "")
    return config


CONFIG = load_config()
AGENT = CONFIG["agent"]


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="校园请假助手 leave_request_agent",
    version=str(AGENT.get("version", "0.1.0")),
    description="北邮校园场景模拟请假 Partner Agent，本地 demo 可运行，保留 ACPs 接入结构。",
    default_response_class=UTF8JSONResponse,
)


def validate_request_context(context: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    student_id = str(context.get("student_id", "")).strip()
    college = str(context.get("college", "")).strip()
    start_time = str(context.get("start_time", "")).strip()
    end_time = str(context.get("end_time", "")).strip()

    if student_id and not re.fullmatch(r"\d{10}", student_id):
        errors.append("学号必须为 10 位数字。")
    if college and college not in ALLOWED_COLLEGES:
        errors.append("学院必须从限定学院列表中选择。")
    if start_time or end_time:
        try:
            start_date = datetime.strptime(start_time, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_time, "%Y-%m-%d").date()
            if end_date < start_date:
                errors.append("请假结束日不能早于请假起始日。")
        except ValueError:
            errors.append("请假起始日和结束日必须使用 YYYY-MM-DD 格式。")
    return errors


def _validation_task_result(task_id: str, errors: List[str]) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        status="error",
        agent_name=str(AGENT.get("name", "校园请假助手")),
        agent_aic=str(AGENT.get("aic", "PLEASE_REPLACE_WITH_REAL_AIC")),
        summary="输入校验失败，请修改后再生成请假分析。",
        data={"validation_errors": errors, "allowed_colleges": ALLOWED_COLLEGES},
        missing_fields=[],
        next_questions=[],
        artifacts=[],
        error="；".join(errors),
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    agent_aic = str(AGENT.get("aic", "PLEASE_REPLACE_WITH_REAL_AIC"))
    footprint_url = get_footprint_url(CONFIG)
    return {
        "status": "ok",
        "agent_name": AGENT.get("name", "校园请假助手"),
        "agent_role": AGENT.get("role", "partner"),
        "agent_aic": agent_aic,
        "version": AGENT.get("version", "0.1.0"),
        "local_demo_mode": bool(AGENT.get("local_demo_mode", True)),
        "acps_ready": agent_aic != "PLEASE_REPLACE_WITH_REAL_AIC" and not bool(AGENT.get("local_demo_mode", True)),
        "footprint_ready": bool(footprint_url),
    }


@app.get("/", response_class=HTMLResponse)
def web_demo() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>校园请假助手</title>
  <style>
    :root {
      color-scheme: light;
      font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
      background: #f6f7fb;
      color: #20242c;
    }
    body {
      margin: 0;
      padding: 28px;
    }
    main {
      max-width: 1120px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(320px, 440px) 1fr;
      gap: 20px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 28px;
      font-weight: 700;
    }
    p {
      margin: 0 0 18px;
      color: #5a6475;
      line-height: 1.6;
    }
    section {
      background: #fff;
      border: 1px solid #e5e8ef;
      border-radius: 8px;
      padding: 18px;
    }
    label {
      display: block;
      margin: 12px 0 6px;
      font-weight: 600;
    }
    input, textarea, select {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #cfd6e4;
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
    }
    .field-error {
      min-height: 22px;
      margin-top: 6px;
      color: #b42318;
      font-size: 14px;
      line-height: 1.4;
    }
    .inline-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .type-options {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 6px;
    }
    .type-option {
      display: flex;
      align-items: center;
      gap: 8px;
      border: 1px solid #cfd6e4;
      border-radius: 6px;
      padding: 10px 12px;
      font-weight: 600;
    }
    .type-option input {
      width: auto;
      margin: 0;
    }
    .readonly-value {
      background: #f3f6fb;
      color: #334155;
    }
    textarea {
      min-height: 98px;
      resize: vertical;
    }
    button {
      margin-top: 14px;
      width: 100%;
      border: 0;
      border-radius: 6px;
      background: #1f6feb;
      color: #fff;
      padding: 11px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled {
      background: #8da9d8;
      cursor: not-allowed;
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #111827;
      color: #e5e7eb;
      border-radius: 8px;
      padding: 16px;
      min-height: 480px;
      overflow: auto;
      margin: 0;
      font-family: Consolas, "Microsoft YaHei", monospace;
      line-height: 1.5;
    }
    .top {
      grid-column: 1 / -1;
    }
    @media (max-width: 860px) {
      body { padding: 16px; }
      main { grid-template-columns: 1fr; }
      .top { grid-column: auto; }
    }
  </style>
</head>
<body>
  <main>
    <div class="top">
      <h1>校园请假助手（本地测试面板）</h1>
      <p>本页面仅用于本地手工测试，不是多智能体协作入口。真实 Leader Agent、个人助手或跨组服务应直接调用 <code>POST /rpc</code>；能力发现使用 <code>GET /acs</code>；调用轨迹由 <code>footprint_client.py</code> 上报。</p>
    </div>
    <section>
      <label>请假类型</label>
      <div class="type-options">
        <label class="type-option">
          <input type="radio" name="leave_type" value="personal_leave" checked />
          事假
        </label>
        <label class="type-option">
          <input type="radio" name="leave_type" value="sick_leave" />
          病假
        </label>
      </div>

      <div class="inline-grid">
        <div>
          <label for="start_date">请假起始日</label>
          <input id="start_date" type="date" value="2026-05-14" />
        </div>
        <div>
          <label for="end_date">请假结束日</label>
          <input id="end_date" type="date" value="2026-05-16" />
        </div>
      </div>
      <div id="date_error" class="field-error"></div>

      <label for="duration">自动检测天数</label>
      <input id="duration" class="readonly-value" value="3 天" readonly />

      <label for="reason">具体原因</label>
      <textarea id="reason">参加挑战杯，行程与课程安排冲突</textarea>
      <div id="reason_error" class="field-error"></div>

      <label for="student_name">姓名</label>
      <input id="student_name" value="张三" />
      <label for="student_id">学号</label>
      <input id="student_id" value="2024000101" inputmode="numeric" />
      <div id="student_id_error" class="field-error"></div>
      <label for="college">学院</label>
      <select id="college">
        <option value="信息与通信工程学院">信息与通信工程学院</option>
        <option value="电子工程学院">电子工程学院</option>
        <option value="人文学院">人文学院</option>
        <option value="国际学院">国际学院</option>
        <option value="网络教育学院">网络教育学院</option>
        <option value="继续教育学院">继续教育学院</option>
        <option value="马克思主义学院">马克思主义学院</option>
        <option value="体育部">体育部</option>
        <option value="现代邮政学院">现代邮政学院</option>
        <option value="计算机学院">计算机学院</option>
        <option value="数字媒体与设计艺术学院">数字媒体与设计艺术学院</option>
        <option value="理学院">理学院</option>
        <option value="经济管理学院">经济管理学院</option>
        <option value="公共管理学院">公共管理学院</option>
        <option value="网络空间安全学院">网络空间安全学院</option>
        <option value="卓越工程师学院">卓越工程师学院</option>
        <option value="数学科学学院">数学科学学院</option>
        <option value="物理科学与技术学院">物理科学与技术学院</option>
      </select>
      <div id="college_error" class="field-error"></div>
      <button id="submit">生成请假分析</button>
    </section>
    <section>
      <pre id="result">等待提交...</pre>
    </section>
  </main>
  <script>
    const result = document.getElementById("result");
    const studentIdInput = document.getElementById("student_id");
    const studentIdError = document.getElementById("student_id_error");
    const collegeInput = document.getElementById("college");
    const collegeError = document.getElementById("college_error");
    const startDateInput = document.getElementById("start_date");
    const endDateInput = document.getElementById("end_date");
    const dateError = document.getElementById("date_error");
    const durationInput = document.getElementById("duration");
    const reasonInput = document.getElementById("reason");
    const reasonError = document.getElementById("reason_error");
    const submitButton = document.getElementById("submit");
    const allowedColleges = new Set([
      "信息与通信工程学院",
      "电子工程学院",
      "人文学院",
      "国际学院",
      "网络教育学院",
      "继续教育学院",
      "马克思主义学院",
      "体育部",
      "现代邮政学院",
      "计算机学院",
      "数字媒体与设计艺术学院",
      "理学院",
      "经济管理学院",
      "公共管理学院",
      "网络空间安全学院",
      "卓越工程师学院",
      "数学科学学院",
      "物理科学与技术学院"
    ]);

    function validateForm() {
      const studentId = studentIdInput.value.trim();
      const college = collegeInput.value.trim();
      const startDate = startDateInput.value;
      const endDate = endDateInput.value;
      const reason = reasonInput.value.trim();
      const errors = [];

      studentIdError.textContent = "";
      collegeError.textContent = "";
      dateError.textContent = "";
      reasonError.textContent = "";

      if (!/^\\d{10}$/.test(studentId)) {
        studentIdError.textContent = "学号必须是 10 位数字，多一位或少一位都不能生成请假分析。";
        errors.push(studentIdError.textContent);
      }
      if (!allowedColleges.has(college)) {
        collegeError.textContent = "学院必须从下拉列表中选择。";
        errors.push(collegeError.textContent);
      }
      if (!startDate || !endDate) {
        dateError.textContent = "请选择请假起始日和请假结束日。";
        durationInput.value = "待选择";
        errors.push(dateError.textContent);
      } else {
        const start = new Date(startDate + "T00:00:00");
        const end = new Date(endDate + "T00:00:00");
        const days = Math.floor((end - start) / 86400000) + 1;
        if (days <= 0) {
          dateError.textContent = "请假结束日不能早于请假起始日。";
          durationInput.value = "日期有误";
          errors.push(dateError.textContent);
        } else {
          durationInput.value = days + " 天";
        }
      }
      if (!reason) {
        reasonError.textContent = "请填写具体请假原因。";
        errors.push(reasonError.textContent);
      }

      submitButton.disabled = errors.length > 0;
      return errors;
    }

    studentIdInput.addEventListener("input", () => {
      studentIdInput.value = studentIdInput.value.replace(/\\D/g, "");
      validateForm();
    });
    collegeInput.addEventListener("change", validateForm);
    startDateInput.addEventListener("change", validateForm);
    endDateInput.addEventListener("change", validateForm);
    reasonInput.addEventListener("input", validateForm);
    validateForm();

    submitButton.addEventListener("click", async () => {
      const validationErrors = validateForm();
      if (validationErrors.length > 0) {
        result.textContent = validationErrors.join("\\n");
        return;
      }
      result.textContent = "正在分析...";
      const leaveType = document.querySelector("input[name='leave_type']:checked").value;
      const leaveTypeLabel = leaveType === "sick_leave" ? "病假" : "事假";
      const durationDays = Number.parseInt(durationInput.value, 10);
      const reason = reasonInput.value.trim();
      const startDate = startDateInput.value;
      const endDate = endDateInput.value;
      const command = `我因${reason}，想从${startDate}到${endDate}请${durationDays}天${leaveTypeLabel}，请帮我生成材料清单、审批流程和请假申请。`;
      const payload = {
        task_id: "web-demo-" + Date.now(),
        source_agent_name: "",
        source_aic: "",
        target_agent_name: "校园请假助手",
        target_aic: "PLEASE_REPLACE_WITH_REAL_AIC",
        user_id: "web-demo-user",
        command,
        context: {
          student_name: document.getElementById("student_name").value,
          student_id: document.getElementById("student_id").value,
          college: document.getElementById("college").value,
          leave_type: leaveType,
          reason,
          start_time: startDate,
          end_time: endDate,
          duration: durationDays + "天"
        }
      };
      try {
        const response = await fetch("/rpc", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        result.textContent = JSON.stringify(data, null, 2);
      } catch (error) {
        result.textContent = "请求失败：" + error;
      }
    });
  </script>
</body>
</html>
"""


@app.get("/acs")
def acs() -> Dict[str, Any]:
    with ACS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@app.post("/rpc", response_model=TaskResult)
def rpc(task: TaskCommand) -> TaskResult:
    try:
        footprint_result = None
        context = dict(task.context or {})
        context.setdefault("source_agent_name", task.source_agent_name)
        context.setdefault("source_aic", task.source_aic)
        validation_errors = validate_request_context(context)
        if validation_errors:
            return _validation_task_result(task.task_id, validation_errors)

        if task.source_aic and task.source_agent_name:
            footprint_result = notify_call(
                task.source_agent_name,
                task.source_aic,
                str(AGENT.get("name", "校园请假助手")),
                str(AGENT.get("aic", "PLEASE_REPLACE_WITH_REAL_AIC")),
                CONFIG,
            )

        result = analyze_leave_request(task.command, context)

        data = dict(result.get("data", {}))
        if footprint_result and not footprint_result.get("ok"):
            data.setdefault("warnings", []).append(footprint_result.get("warning", "Footprint 上报失败。"))

        return TaskResult(
            task_id=task.task_id,
            status=result["status"],
            agent_name=str(AGENT.get("name", "校园请假助手")),
            agent_aic=str(AGENT.get("aic", "PLEASE_REPLACE_WITH_REAL_AIC")),
            summary=result["summary"],
            data=data,
            missing_fields=result.get("missing_fields", []),
            next_questions=result.get("next_questions", []),
            artifacts=_build_artifacts(data),
            error=result.get("error"),
        )
    except Exception as exc:
        return TaskResult(
            task_id=task.task_id,
            status="error",
            agent_name=str(AGENT.get("name", "校园请假助手")),
            agent_aic=str(AGENT.get("aic", "PLEASE_REPLACE_WITH_REAL_AIC")),
            summary="请假助手处理任务时发生异常。",
            data={},
            missing_fields=[],
            next_questions=[],
            artifacts=[],
            error=str(exc),
        )


@app.post("/leave/analyze")
def leave_analyze(request: LeaveAnalyzeRequest) -> Dict[str, Any]:
    try:
        validation_errors = validate_request_context(request.context)
        if validation_errors:
            return {
                "status": "error",
                "summary": "输入校验失败，请修改后再生成请假分析。",
                "data": {"validation_errors": validation_errors, "allowed_colleges": ALLOWED_COLLEGES},
                "error": "；".join(validation_errors),
            }
        return analyze_leave_request(request.command, request.context)
    except Exception as exc:
        return {"status": "error", "summary": "分析请假需求时发生异常。", "data": {}, "error": str(exc)}


@app.post("/leave/draft")
def leave_draft(request: LeaveDraftRequest) -> Dict[str, Any]:
    try:
        validation_errors = validate_request_context(request.context)
        if validation_errors:
            return {
                "status": "error",
                "draft_application": "",
                "missing_fields": [],
                "next_questions": [],
                "error": "；".join(validation_errors),
            }
        analysis = analyze_leave_request(request.command, request.context)
        fields = analysis.get("data", {}).get("extracted_fields", {})
        leave_type = analysis.get("data", {}).get("leave_type")
        return {
            "status": analysis.get("status"),
            "draft_application": generate_draft(fields, leave_type),
            "missing_fields": analysis.get("missing_fields", []),
            "next_questions": analysis.get("next_questions", []),
        }
    except Exception as exc:
        return {"status": "error", "draft_application": "", "missing_fields": [], "next_questions": [], "error": str(exc)}


def _build_artifacts(data: Dict[str, Any]) -> list[Dict[str, Any]]:
    draft = data.get("draft_application")
    if not draft:
        return []
    return [{"type": "text", "name": "leave_application_draft", "content": draft}]
