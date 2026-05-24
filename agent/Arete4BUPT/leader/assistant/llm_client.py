"""OpenAI 兼容的 LLM 调用封装."""

import json
import logging
from string import Template
from openai import OpenAI

from .config import get_config

logger = logging.getLogger(__name__)


def _build_client(profile: str = "default") -> OpenAI:
    cfg = get_config().llm(profile)
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])


def chat(
    system_prompt: str,
    user_message: str,
    profile: str = "default",
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    """调用 LLM，返回文本结果."""
    client = _build_client(profile)
    logger.debug("LLM [%s] system=%s... user=%s...", profile, system_prompt[:80], user_message[:80])
    resp = client.chat.completions.create(
        model=get_config().llm(profile).get("model", ""),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = resp.choices[0].message.content or ""
    logger.debug("LLM response: %s...", content[:120])
    return content


def chat_json(
    system_prompt: str,
    user_message: str,
    profile: str = "default",
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> dict:
    """调用 LLM，返回解析后的 JSON dict."""
    raw = chat(system_prompt, user_message, profile=profile, temperature=temperature, max_tokens=max_tokens)
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    return json.loads(raw)
