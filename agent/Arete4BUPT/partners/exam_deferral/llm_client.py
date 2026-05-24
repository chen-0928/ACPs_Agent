"""LLM 客户端 - 调用大模型 API，失败自动降级到本地知识库"""

import httpx
import tomli
from pathlib import Path
from typing import Optional

from knowledge import answer as kb_answer


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.toml"
    with open(config_path, "rb") as f:
        return tomli.load(f)


def load_prompts() -> dict:
    prompts_path = Path(__file__).parent / "prompts.toml"
    with open(prompts_path, "rb") as f:
        return tomli.load(f)


async def call_llm(
    user_query: str,
    intent: str = "",
    history: Optional[list[dict]] = None,
) -> dict:
    """
    调用 LLM 完成三阶段推理并返回 {answer, skills, source}。
    若 LLM 不可用，自动降级到本地知识库。
    """
    config = load_config()
    prompts = load_prompts()

    llm_cfg = config["llm"]
    api_key = llm_cfg.get("api_key", "")
    base_url = llm_cfg.get("base_url", "")
    model = llm_cfg.get("model", "qwen-plus")

    if not api_key:
        return _fallback(user_query)

    # 阶段一：理解用户意图
    understanding_prompt = prompts["understanding"]["system"]
    # 阶段二：规划回复
    planning_prompt = prompts["planning"]["system"]
    # 阶段三：执行生成
    execution_prompt = prompts["execution"]["system"]

    combined_system = f"""{understanding_prompt}

---

{planning_prompt}

---

{execution_prompt}"""

    messages = [{"role": "system", "content": combined_system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_query})

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": llm_cfg.get("temperature", 0.7),
                    "max_tokens": llm_cfg.get("max_tokens", 2048),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            kb = kb_answer(user_query)
            return {
                "answer": content,
                "skills": kb["skills"],
                "intent": kb["intent"],
                "reason": kb["reason"],
                "source": "llm",
            }
    except Exception as e:
        print(f"[LLM Error] {e}, 降级到本地知识库")
        return _fallback(user_query)


def _fallback(query: str) -> dict:
    """本地知识库兜底"""
    kb = kb_answer(query)
    return {
        "answer": kb["answer"],
        "skills": kb["skills"],
        "intent": kb["intent"],
        "reason": kb["reason"],
        "source": "local_knowledge_base",
    }

