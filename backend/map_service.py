"""地图工具：内置坐标优先，未命中则走高德 Web 服务实时检索。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# 经纬度：高德/国测局 GCJ-02（常用点，免额度）
PLACE_LIBRARY: dict[str, dict[str, Any]] = {
    "保定理工学院": {
        "name": "保定理工学院",
        "lng": 115.485083,
        "lat": 38.814709,
        "address": "河北省保定市南大园乡南二环1689号",
        "aliases": ["保理学院", "保定理工", "中国地质大学长城学院"],
    },
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
    r"(在哪|哪里|哪儿|位置|坐标|地图|定位|点位|怎么走|导航|经纬度|打卡|地址)",
    re.I,
)

_NOISE_PREFIX = re.compile(
    r"^(请问|帮我|麻烦|我想|请您?|查一下|帮查|搜索|查询|找一下|看一下)+"
)


def amap_web_key() -> str:
    """Web服务 Key（地理编码 / 关键词检索），与前端 JS Key 不同。"""
    return (
        os.getenv("AMAP_WEB_KEY")
        or os.getenv("AMAP_GEOCODE_KEY")
        or ""
    ).strip()


def realtime_enabled() -> bool:
    return bool(amap_web_key())


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
    pairs.sort(key=lambda x: len(x[0]), reverse=True)
    return pairs


def extract_place_name(text: str) -> str | None:
    """命中内置库时返回库 key。"""
    t = (text or "").strip()
    if not t:
        return None
    for alias, key in _alias_index():
        if alias in t:
            return key
    return None


def extract_query_text(text: str) -> str:
    """从自然语言抽出待检索地名（保留完整词，如「保定西大街」不砍成「保定」）。"""
    t = (text or "").strip()
    t = _NOISE_PREFIX.sub("", t)
    # 只剥句尾意图词，避免「保定位置」被「定位」误切成「保置」
    t = re.sub(
        r"(的)?(在哪[里儿]?|位置|坐标|地图|定位|点位|怎么走|导航|经纬度|打卡|地址)+$",
        "",
        t,
    )
    t = re.sub(r"[？?。！!，,、：:\s]+", "", t)
    for noise in ("一下", "看看", "告诉我", "是多少"):
        if t.endswith(noise) and len(t) > len(noise) + 1:
            t = t[: -len(noise)]
    return t.strip()


def _builtin_names(key: str) -> set[str]:
    meta = PLACE_LIBRARY[key]
    return {key, meta["name"], *(meta.get("aliases") or [])}


def _is_exact_builtin_query(query: str, key: str) -> bool:
    """查询是否正好是内置地名（而不是「保定西大街」这种更长地点）。"""
    return (query or "").strip() in _builtin_names(key)


def is_map_question(text: str) -> bool:
    """地理位置提问：内置地名，或「xx在哪」类实时检索意图。"""
    t = (text or "").strip()
    if not t:
        return False
    if any(k in t for k in ("天气", "气温", "下雨", "穿什么", "穿搭", "多少度")):
        return False

    builtin = extract_place_name(t)
    if builtin and _GEO_HINT.search(t):
        return True
    if builtin and any(k in t for k in ("介绍", "看看", "打开", "显示", "标记", "定位")):
        return True
    stripped = re.sub(r"[？?。！!\s哟啊呢吗嘛]", "", t)
    if stripped in PLACE_LIBRARY:
        return True
    for alias, _key in _alias_index():
        if stripped == alias:
            return True

    # 实时：带定位意图词，且抽得出地名
    if _GEO_HINT.search(t):
        q = extract_query_text(t)
        if len(q) >= 2:
            return True
    return False


def _builtin_point(key: str) -> dict:
    meta = PLACE_LIBRARY[key]
    return {
        "name": meta["name"],
        "lng": float(meta["lng"]),
        "lat": float(meta["lat"]),
        "address": meta["address"],
        "source": "builtin",
    }


def _parse_location(loc: str) -> tuple[float, float] | None:
    parts = (loc or "").split(",")
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _amap_get(url: str, params: dict) -> dict:
    with httpx.Client(timeout=12.0) as client:
        r = client.get(url, params=params)
        return r.json()


def _raise_amap_status(data: dict, query: str) -> None:
    info = (data.get("info") or "").upper()
    if info in ("INVALID_USER_KEY", "USERKEY_PLAT_NOMATCH"):
        raise ValueError(
            "高德 Web服务 Key 无效或类型不对。请确认 backend/.env 的 "
            "AMAP_WEB_KEY 是「Web服务」类型（不要填 JS Key）。"
        )
    if info in ("DAILY_QUERY_OVER_LIMIT", "ACCESS_TOO_FREQUENT", "CUQPS_HAS_EXCEEDED_THE_LIMIT"):
        raise ValueError("高德调用超限，请稍后再试或提升配额。")
    if str(data.get("status")) != "1" and info and info not in ("OK", "ENGINE_RESPONSE_DATA_ERROR"):
        # 无结果时 status 也可能是 1 + 空列表；其它错误直接抛
        if info not in ("", "UNKNOWN_ERROR"):
            raise ValueError(f"高德检索失败（{data.get('info')}）：{query}")


def _guess_city(query: str) -> str:
    """从查询里带出城市，提高街道/小区检索精度。"""
    q = query or ""
    cities = (
        "北京",
        "上海",
        "天津",
        "重庆",
        "保定",
        "石家庄",
        "邯郸",
        "唐山",
        "廊坊",
        "沧州",
        "张家口",
        "承德",
        "衡水",
        "邢台",
        "秦皇岛",
    )
    for city in cities:
        if q.startswith(city) or q.startswith(city + "市"):
            return city
    # 「保定西大街」这类：城市在中间/开头但不整句等于城市名
    for city in cities:
        if city in q and q != city and q != city + "市":
            return city
    return ""


def _amap_place_search(query: str, key: str) -> dict | None:
    """关键词 POI 检索（适合学校、景点、商场、街道等）。"""
    params: dict[str, Any] = {
        "key": key,
        "keywords": query,
        "offset": 1,
        "page": 1,
        "extensions": "base",
    }
    city = _guess_city(query)
    if city:
        params["city"] = city
    data = _amap_get(
        "https://restapi.amap.com/v3/place/text",
        params,
    )
    if str(data.get("status")) != "1":
        _raise_amap_status(data, query)
        return None
    pois = data.get("pois") or []
    if not pois:
        return None
    poi = pois[0]
    xy = _parse_location(poi.get("location") or "")
    if not xy:
        return None
    name = (poi.get("name") or query).strip()
    addr = (poi.get("address") or "").strip()
    if isinstance(addr, list):
        addr = "".join(str(x) for x in addr)
    city = (poi.get("cityname") or poi.get("pname") or "").strip()
    if isinstance(city, list):
        city = "".join(str(x) for x in city)
    if city and addr and city not in addr:
        addr = f"{city}{addr}"
    elif not addr:
        addr = city or name
    return {
        "name": name,
        "lng": xy[0],
        "lat": xy[1],
        "address": addr,
        "source": "amap_poi",
    }


def _amap_geocode(query: str, key: str) -> dict | None:
    """地址地理编码。"""
    data = _amap_get(
        "https://restapi.amap.com/v3/geocode/geo",
        {"key": key, "address": query},
    )
    if str(data.get("status")) != "1":
        _raise_amap_status(data, query)
        return None
    geos = data.get("geocodes") or []
    if not geos:
        return None
    g = geos[0]
    xy = _parse_location(g.get("location") or "")
    if not xy:
        return None
    addr = (g.get("formatted_address") or query).strip()
    if isinstance(addr, list):
        addr = "".join(str(x) for x in addr)
    name = query.strip() or addr
    return {
        "name": name,
        "lng": xy[0],
        "lat": xy[1],
        "address": addr,
        "source": "amap_geo",
    }


def amap_realtime(query: str) -> dict:
    key = amap_web_key()
    if not key:
        raise ValueError(
            "未配置 AMAP_WEB_KEY（高德控制台「Web服务」类型 Key）。"
            "配置后即可实时检索任意地点。"
        )
    q = (query or "").strip()
    if len(q) < 2:
        raise ValueError("请提供更完整的地名")

    # 含路/街/号 → 先地理编码；学校商场等 → 先 POI
    address_like = bool(re.search(r"[路街道巷号门弄苑区园]", q))
    if address_like:
        point = _amap_geocode(q, key) or _amap_place_search(q, key)
    else:
        point = _amap_place_search(q, key) or _amap_geocode(q, key)
    if point is None:
        raise ValueError(f"未找到「{q}」，请换个更具体的名称再试（可加城市，如：保定西大街）")
    return point


def geocode_place(place: str) -> dict:
    """默认高德实时定位具体点；仅当输入正好是内置简称时用内置坐标。"""
    raw = (place or "").strip()
    if not raw:
        raise ValueError("请提供地名")

    query = extract_query_text(raw) or raw
    builtin_key = extract_place_name(query) or extract_place_name(raw)
    # 只有整句就是「保定」「白洋淀」等才用内置；「保定西大街」必须实时搜
    if builtin_key and _is_exact_builtin_query(query, builtin_key):
        return _builtin_point(builtin_key)

    return amap_realtime(query)


def format_map_answer(point: dict) -> str:
    name = point["name"]
    lng = point["lng"]
    lat = point["lat"]
    addr = point.get("address") or ""
    src = point.get("source") or ""
    src_tip = {
        "builtin": "内置坐标",
        "amap_poi": "高德实时检索",
        "amap_geo": "高德地理编码",
    }.get(src, "地图服务")
    return (
        f"已为你定位到 **{name}**（{src_tip}）。\n\n"
        f"- 地址：{addr}\n"
        f"- 经度：{lng}\n"
        f"- 纬度：{lat}\n\n"
        f"右侧地图已同步标记该点位。\n\n"
        f"[[map:{lng},{lat},{name}]]"
    )


def try_resolve_map(question: str) -> dict | None:
    """对话侧：地图意图则解析坐标；失败时返回带说明的伪结果由上层当 answer。"""
    if not is_map_question(question):
        return None
    try:
        return geocode_place(question)
    except ValueError as e:
        # 让 chat 仍能回复可读错误，而不是静默走 LLM
        return {"_error": str(e)}


def format_map_error(err: str) -> str:
    return (
        f"⚠️ 定位失败\n\n{err}\n\n"
        "可试：更具体的地名（城市+地点），或检查服务器是否配置了 "
        "`AMAP_WEB_KEY`（高德 Web服务 Key）。"
    )


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
