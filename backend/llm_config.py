"""对话大模型配置：优先智谱，其次兼容旧的 QIANWEN_* 变量。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def reload_env() -> None:
    load_dotenv(_ENV_PATH, override=True)


def get_chat_llm_config() -> dict[str, str] | None:
    """返回 {api_key, base_url, model, provider}；未配置 Key 时返回 None。"""
    reload_env()

    zhipu_key = (os.getenv("ZHIPU_API_KEY") or "").strip()
    if zhipu_key:
        return {
            "api_key": zhipu_key,
            "base_url": (
                os.getenv("ZHIPU_BASE_URL")
                or "https://open.bigmodel.cn/api/paas/v4"
            ).rstrip("/"),
            "model": (os.getenv("ZHIPU_MODEL") or "glm-4-flash").strip(),
            "provider": "zhipu",
        }

    # 兼容：把 QIANWEN_* 指到智谱或其他 OpenAI 兼容服务
    q_key = (os.getenv("QIANWEN_API_KEY") or "").strip()
    if q_key:
        return {
            "api_key": q_key,
            "base_url": (
                os.getenv("QIANWEN_BASE_URL")
                or "https://open.bigmodel.cn/api/paas/v4"
            ).rstrip("/"),
            "model": (os.getenv("QIANWEN_MODEL") or "glm-4-flash").strip(),
            "provider": "openai-compatible",
        }

    return None
