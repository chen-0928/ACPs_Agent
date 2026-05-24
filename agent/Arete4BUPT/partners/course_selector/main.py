"""Arete4BUPT Partner Agent — 选课助手（最终交付版）"""

import json
import toml
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from footprint_sdk import report_call_sync

AGENT_NAME = "选课助手"
AGENT_AIC = "1.2.156.3088.0001.00001.D614VG.000000.1.04CH"

app = FastAPI(title="Arete4BUPT 选课助手", version="1.0.0")


# ----------------------
# 请求 / 响应模型
# ----------------------
class TaskRequest(BaseModel):
    task_id: str
    command: str
    payload: dict


class TaskResponse(BaseModel):
    task_id: str
    status: str
    result: dict


# ----------------------
# LLM 调用（✅ 稳定版）
# ----------------------
def call_llm(
    system_prompt: str,
    user_prompt: str,
    llm_cfg: dict,
    temperature: float = 0.1,
    timeout: float = 30.0
) -> dict:
    try:
        resp = httpx.post(
            f"{llm_cfg['base_url'].rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {llm_cfg['api_key']}",
                "Content-Type": "application/json"
            },
            json={
                "model": llm_cfg["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature
            },
            timeout=timeout
        )

        if resp.status_code != 200:
            return {"error": f"LLM调用失败，状态码：{resp.status_code}"}

        content = resp.json()["choices"][0]["message"]["content"]

        if not content or not content.strip():
            return {"error": "LLM返回内容为空"}

        # ✅ 尝试解析 JSON，失败则当作纯文本
        try:
            return json.loads(content)
        except Exception:
            return {"message": content.strip()}

    except Exception as e:
        return {"error": f"LLM处理异常：{str(e)}"}


# ----------------------
# Production 结果提取
# ----------------------
def extract_production_message(obj) -> str:
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict):
        for k in ("message", "reply", "content", "text"):
            if k in obj and isinstance(obj[k], str):
                return obj[k].strip()
        return json.dumps(obj, ensure_ascii=False)
    return str(obj)


# ----------------------
# 路由
# ----------------------
@app.get("/health")
def health():
    return {"status": "ok", "agent": "选课助手"}


@app.post("/rpc")
def handle_task(req: TaskRequest):
    # ★ 协作前上报 Footprint
    report_call_sync("个人课程助手Leader",
                     "1.2.156.3088.0001.00001.R1JUQE.821HRL.1.0YVV",
                     AGENT_NAME, AGENT_AIC)
    try:
        # 1. 加载配置
        try:
            config = toml.load("config.toml")
            prompts = toml.load("prompts.toml")
        except Exception as e:
            return TaskResponse(
                task_id=req.task_id,
                status="failed",
                result={"message": f"配置文件加载失败: {str(e)}"}
            )

        user_message = req.payload.get("message", "")
        original_message = req.payload.get("original_message", {})
        depends_on_result = req.payload.get("depends_on_result", None)

        fast_llm = config["llm"]["fast"]

        # ==========================================
        # Phase 1: Decision（准入判断）
        # ==========================================
        decision_sys = prompts["decision"]["system"]
        decision_usr = prompts["decision"]["user"].format(
            request_body=user_message
        )

        decision_result = call_llm(decision_sys, decision_usr, fast_llm)
        if "error" in decision_result:
            return TaskResponse(
                task_id=req.task_id,
                status="failed",
                result={"message": decision_result["error"]}
            )

        is_partial = decision_result.get("partial", False)
        reject_items = decision_result.get("reject_items", [])

        if not decision_result.get("accepted", False):
            if not is_partial:
                return TaskResponse(
                    task_id=req.task_id,
                    status="failed",
                    result={
                        "message": decision_result.get(
                            "reason", "不在选课助手服务范围内"
                        )
                    }
                )

        # ==========================================
        # Phase 2: Analysis（需求分析）
        # ==========================================
        analysis_sys = prompts["analysis"]["system"]
        analysis_usr = prompts["analysis"]["user"].format(
            original_request=user_message,
            context=json.dumps({
                "original_message": original_message,
                "depends_on_result": depends_on_result
            }, ensure_ascii=False)
        )

        analysis_result = call_llm(analysis_sys, analysis_usr, fast_llm)
        if "error" in analysis_result:
            return TaskResponse(
                task_id=req.task_id,
                status="failed",
                result={"message": analysis_result["error"]}
            )

        # ✅ 空消息兜底
        if not user_message or not user_message.strip():
            return TaskResponse(
                task_id=req.task_id,
                status="failed",
                result={"message": "请求内容为空，无法处理"}
            )

        if not analysis_result.get("is_complete", True):
            return TaskResponse(
                task_id=req.task_id,
                status="awaiting_input",
                result={
                    "message": analysis_result.get(
                        "clarification_question", "请补充选课相关信息"
                    )
                }
            )

        # ==========================================
        # Phase 3: Production（内容生成）
        # ==========================================
        production_sys = prompts["production"]["system"]

        # ✅ mock 数据（可按 intent 精简）
        mock_course_data = [
            {"name": "深度学习", "credit": 3, "prereq": "Python, 线性代数", "capacity": "剩余10人"},
            {"name": "计算机视觉", "credit": 2, "prereq": "深度学习", "capacity": "已满"},
            {"name": "自然语言处理", "credit": 3, "prereq": "机器学习", "capacity": "剩余25人"}
        ]

        production_usr = prompts["production"]["user"].format(
            params=json.dumps(
                analysis_result.get("extracted_params", {}),
                ensure_ascii=False
            ),
            course_data=json.dumps(mock_course_data, ensure_ascii=False)
        )

        production_result = call_llm(
            production_sys,
            production_usr,
            fast_llm,
            temperature=0.3,
            timeout=30.0
        )

        if "error" in production_result:
            return TaskResponse(
                task_id=req.task_id,
                status="failed",
                result={"message": production_result["error"]}
            )

        final_message = extract_production_message(production_result)
        if not final_message:
            final_message = "选课助手暂时无法生成建议，请稍后再试。"

        # ✅ 混合请求追加拒绝说明
        if is_partial and reject_items:
            reject_text = "、".join(reject_items)
            final_message += (
                f"\n\n（温馨提示：{reject_text}相关请求不在选课助手服务范围内，"
                f"我已为你完成选课部分的解答。）"
            )

        return TaskResponse(
            task_id=req.task_id,
            status="completed",
            result={"message": final_message}
        )

    except Exception as e:
        return TaskResponse(
            task_id=req.task_id,
            status="failed",
            result={"message": f"服务处理异常: {str(e)}"}
        )


# ----------------------
# 启动入口
# ----------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=59221, reload=True)