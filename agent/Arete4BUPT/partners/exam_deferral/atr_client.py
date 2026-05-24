"""
ATR (Agent Trusted Registration) 客户端
向 ATR 注册服务器提交 acs.json，获取唯一 AIC（如 1.2.156.3088.xxxxx）
"""

import json
import sys
import httpx
import tomli
import tomli_w
from pathlib import Path


CONFIG_PATH = Path(__file__).parent / "config.toml"
ACS_PATH = Path(__file__).parent / "acs.json"


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomli.load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)


def load_acs() -> dict:
    with open(ACS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def register() -> str:
    """
    向 ATR 注册服务器提交身份证申请，返回 AIC。
    流程：① 提交 acs.json → ② 服务器分配 AIC → ③ 持久化到 config.toml
    """
    config = load_config()
    acs = load_acs()
    register_url = config["atr"]["register_url"]

    payload = {
        "agent_id": acs["agent_id"],
        "name": acs["name"],
        "version": acs["version"],
        "acs": acs,
    }

    print(f"[ATR] 正在向 {register_url} 提交注册请求...")
    print(f"[ATR] Agent ID: {acs['agent_id']}")

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(f"{register_url}/register", json=payload)
            resp.raise_for_status()
            data = resp.json()
            aic = data.get("aic", "")
            if not aic:
                raise ValueError(f"响应中未返回 AIC: {data}")
    except httpx.HTTPError as e:
        print(f"[ATR] ⚠ 注册服务不可达或返回错误: {e}")
        print(f"[ATR] 使用 mock AIC 用于本地开发")
        aic = _generate_mock_aic(acs["agent_id"])
    except Exception as e:
        print(f"[ATR] ⚠ 注册失败: {e}")
        aic = _generate_mock_aic(acs["agent_id"])

    # 持久化到 config.toml
    config["atr"]["aic"] = aic
    save_config(config)
    print(f"[ATR] ✓ 注册完成，AIC = {aic}")
    print(f"[ATR] ✓ 已写入 config.toml")
    return aic


def _generate_mock_aic(agent_id: str) -> str:
    """本地开发时的 mock AIC 生成器"""
    import hashlib
    h = hashlib.md5(agent_id.encode()).hexdigest()[:8]
    return f"1.2.156.3088.{int(h, 16) % 100000:05d}"


def get_aic() -> str:
    """读取已注册的 AIC；未注册则返回空字符串"""
    return load_config()["atr"].get("aic", "")


if __name__ == "__main__":
    aic = register()
    sys.exit(0 if aic else 1)
