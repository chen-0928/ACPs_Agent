"""加载 config.toml 并暴露配置项."""

from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # 需要 pip install tomli

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"config.toml 不存在: {path}\n"
            "请复制 config.example.toml 为 config.toml 并填入配置: "
            f"cp {ROOT / 'config.example.toml'} {path}"
        )
    with open(path, "rb") as f:
        return tomllib.load(f)


class AppConfig:
    """包一层，方便各模块获取具体配置."""

    def __init__(self, raw: dict):
        self.raw = raw

    def llm(self, profile: str = "default") -> dict:
        return self.raw.get("llm", {}).get(profile, {})

    @property
    def discovery_url(self) -> str:
        return self.raw.get("discovery", {}).get("server_base_url", "")

    @property
    def discovery_limit(self) -> int:
        return self.raw.get("discovery", {}).get("limit", 5)

    @property
    def port(self) -> int:
        return self.raw.get("uvicorn", {}).get("port", 59210)

    @property
    def host(self) -> str:
        return self.raw.get("uvicorn", {}).get("host", "0.0.0.0")


_CONFIG: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _CONFIG
    if _CONFIG is None:
        raw = load_config()
        _CONFIG = AppConfig(raw)
    return _CONFIG
