"""简易联网检索：DuckDuckGo Instant Answer（免费、无需 Key）。"""
from __future__ import annotations

import re
from typing import Optional

import httpx

_SEARCH_RE = re.compile(
    r"(搜索|查一下|帮我查|最新消息|新闻|股价|汇率|今天是几号|现在几点)",
    re.I,
)


def is_search_question(text: str) -> bool:
    t = text or ""
    if is_probably_chitchat(t):
        return False
    return bool(_SEARCH_RE.search(t))


def is_probably_chitchat(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2:
        return True
    return bool(re.match(r"^(你好|您好|在吗|嗨|hi|hello)[\s!！.。]*$", t, re.I))


def fetch_search(question: str) -> Optional[str]:
    q = (question or "").strip()
    if not q:
        return None
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            r = client.get(
                "https://api.duckduckgo.com/",
                params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            r.raise_for_status()
            data = r.json() or {}
    except Exception:
        return None

    parts: list[str] = []
    abstract = (data.get("AbstractText") or "").strip()
    heading = (data.get("Heading") or "").strip()
    source = (data.get("AbstractURL") or "").strip()
    if abstract:
        title = heading or "检索结果"
        parts.append(f"【联网摘要 · {title}】")
        parts.append(abstract)
        if source:
            parts.append(f"来源：{source}")

    related = data.get("RelatedTopics") or []
    bullets = []
    for item in related:
        if not isinstance(item, dict):
            continue
        text = (item.get("Text") or "").strip()
        if text:
            bullets.append(f"- {text}")
        if len(bullets) >= 5:
            break
    if bullets and not abstract:
        parts.append("【相关条目】")
        parts.extend(bullets)

    answer = (data.get("Answer") or "").strip()
    if answer:
        parts.insert(0, f"速答：{answer}")

    if not parts:
        return (
            "联网检索暂未找到直接摘要（部分中文问题结果较少）。"
            "你可以换关键词，或问具体城市天气（已支持实时天气）。"
        )
    parts.append("")
    parts.append("数据来源：DuckDuckGo Instant Answer")
    return "\n".join(parts)
