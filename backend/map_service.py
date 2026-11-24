"""地图工具：内置地点坐标库（不走高德地理编码，避免额度）。"""
from __future__ import annotations

import re
from typing import Any

# 经纬度：高德/国测局 GCJ-02 常用点位（录屏可真实落点）
PLACE_LIBRARY: dict[str, dict[str, Any]] = {
    "保定": {
        "name": "保定",
        "lng": 115.4648,
        "lat": 38.8739,
        "address": "河北省保定市",
        "aliases": ["保定市", "保定市区"],
    },
    "白洋淀": {
        "name": "白洋淀",
        "lng": 115.9350,
        "lat": 38.9225,
        "address": "河北省保定市安新县白洋淀",
        "aliases": ["白洋淀景区", "安新白洋淀"],
    },
    "狼牙山": {
        "name": "狼牙山",
        "lng": 115.2360,
        "lat": 39.1450,
        "address": "河北省保定市易县狼牙山",
        "aliases": ["狼牙山景区", "易县狼牙山"],
    },
}

_GEO_HINT = re.compile(
    r"(在哪|哪里|哪儿|位置|坐标|地图|定位|点位|怎么走|导航|经纬度|打卡)",
    re.I,
)


def list_places() -> list[dict]:
    return [
        {
            "key": k,
            "name": v["name"],
            "lng": v["lng"],
            "lat": v["lat"],
            "address": v["address"],
        }
        for k, v in PLACE_LIBRARY.items()
    ]


def _alias_index() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, meta in PLACE_LIBRARY.items():
        pairs.append((key, key))
        for a in meta.get("aliases") or []:
            pairs.append((a, key))
    # 长词优先，避免短词误伤
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def extract_place_name(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    for alias, key in _alias_index():
        if alias in t:
            return key
    return None


def is_map_question(text: str) -> bool:
    """是否像地理位置提问：含内置地名，且带定位意图（避免抢天气等问题）。"""
    t = (text or "").strip()
    if not t:
        return False
    # 天气/穿搭留给对应能力
    if any(k in t for k in ("天气", "气温", "下雨", "穿什么", "穿搭", "多少度")):
        return False
    place = extract_place_name(t)
    if not place:
        return False
    if _GEO_HINT.search(t):
        return True
    if any(k in t for k in ("介绍", "看看", "打开", "显示", "标记", "定位")):
        return True
    # 仅地名本身 / 地名+语气词
    stripped = re.sub(r"[？?。！!\s哟啊呢吗嘛]", "", t)
    if stripped in PLACE_LIBRARY:
        return True
    for alias, key in _alias_index():
        if stripped == alias:
            return True
    return False


def geocode_place(place: str) -> dict:
    """根据地名返回坐标。未命中抛 ValueError。"""
    raw = (place or "").strip()
    if not raw:
        raise ValueError("请提供地名，例如：保定、白洋淀、狼牙山")

    key = extract_place_name(raw) or raw
    # 允许直接传标准名
    if key not in PLACE_LIBRARY:
        for alias, k in _alias_index():
            if alias == raw or alias in raw:
                key = k
                break
    meta = PLACE_LIBRARY.get(key)
    if meta is None:
        supported = "、".join(PLACE_LIBRARY.keys())
        raise ValueError(f"暂不支持该地点。当前内置：{supported}")

    return {
        "name": meta["name"],
        "lng": float(meta["lng"]),
        "lat": float(meta["lat"]),
        "address": meta["address"],
        "source": "builtin",
    }


def format_map_answer(point: dict) -> str:
    name = point["name"]
    lng = point["lng"]
    lat = point["lat"]
    addr = point.get("address") or ""
    # 前端解析：[[map:lng,lat,name]]
    return (
        f"已为你定位到 **{name}**。\n\n"
        f"- 地址：{addr}\n"
        f"- 经度：{lng}\n"
        f"- 纬度：{lat}\n\n"
        f"右侧地图已同步标记该点位。\n\n"
        f"[[map:{lng},{lat},{name}]]"
    )


def try_resolve_map(question: str) -> dict | None:
    """对话侧：若命中地图意图则返回坐标结果，否则 None。"""
    if not is_map_question(question):
        return None
    place = extract_place_name(question)
    if not place:
        return None
    return geocode_place(place)


_MAP_MARKER_RE = re.compile(
    r"\[\[map:([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([^\]]+)\]\]"
)


def parse_map_marker(text: str) -> dict | None:
    m = _MAP_MARKER_RE.search(text or "")
    if not m:
        return None
    try:
        return {
            "lng": float(m.group(1)),
            "lat": float(m.group(2)),
            "name": m.group(3).strip(),
        }
    except ValueError:
        return None


def strip_map_marker(text: str) -> str:
    return _MAP_MARKER_RE.sub("", text or "").rstrip()
