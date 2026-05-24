from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class LLMClient:
    """Optional LLM adapter. The rule engine remains the default reliable path."""

    def __init__(self, config: Dict[str, Any]):
        llm_config = config.get("llm", {})
        self.enabled = bool(llm_config.get("enabled", False))
        self.base_url = str(llm_config.get("base_url", "")).strip()
        self.api_key = str(llm_config.get("api_key", "")).strip()
        self.model = str(llm_config.get("model", "qwen3-8b"))
        self.timeout = float(llm_config.get("timeout", 30))

    def available(self) -> bool:
        return self.enabled and bool(self.base_url and self.api_key)

    async def complete(self, prompt: str) -> Optional[str]:
        if not self.available():
            return None

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        return body.get("choices", [{}])[0].get("message", {}).get("content")
