"""行程规划工具：生成一日游建议，并按顺序输出地图打点标记。"""
from __future__ import annotations

import re

from map_service import PLACE_LIBRARY, amap_realtime

_ROUTE_HINT = re.compile(
    r"(一日游|两日游|行程|路线规划|旅游路线|游玩路线|怎么玩|规划.*(游|行程|路线))",
    re.I,
)

# 示例目的地预设（演示用，可继续扩展）
_PRESETS: dict[str, list[dict]] = {
    "保定": [
        {"slot": "上午", "name": "直隶总督署博物馆", "tip": "了解清代直隶政治文化，建议1～1.5小时"},
        {"slot": "上午", "name": "古莲花池", "tip": "古典园林散步拍照，紧邻总督署"},
        {"slot": "中午", "name": "保定西大街", "tip": "午餐+逛历史文化街区"},
        {"slot": "下午", "name": "保定军校纪念馆", "tip": "红色/近代军事史，适合研学"},
        {"slot": "傍晚", "name": "竞秀公园", "tip": "休闲散步收尾，可看夜景"},
    ],
    "白洋淀": [
        {"slot": "上午", "name": "白洋淀", "tip": "乘船游淀，观荷听芦"},
        {"slot": "中午", "name": "白洋淀", "tip": "淀区渔家餐（请按景区指示选择正规餐厅）"},
        {"slot": "下午", "name": "白洋淀", "tip": "继续水上项目或文化展馆"},
        {"slot": "傍晚", "name": "安新", "tip": "返程前可在安新县城稍作停留"},
    ],
    "狼牙山": [
        {"slot": "上午", "name": "狼牙山", "tip": "红色教育登山，注意防滑与体力"},
        {"slot": "中午", "name": "狼牙山", "tip": "景区附近简餐"},
        {"slot": "下午", "name": "狼牙山", "tip": "参观五勇士相关纪念设施"},
        {"slot": "傍晚", "name": "易县", "tip": "下山返回易县/保定市区"},
    ],
}

# 预设景点内置坐标（GCJ-02）：高德超限时一日游仍可打点演示
_SPOT_COORDS: dict[str, dict] = {
    "直隶总督署博物馆": {
        "name": "保定直隶总督署博物馆",
        "lng": 115.497234,
        "lat": 38.859794,
        "address": "河北省保定市裕华路301号",
    },
    "古莲花池": {
        "name": "古莲花池",
        "lng": 115.498127,
        "lat": 38.857503,
        "address": "河北省保定市莲池南大街246号",
    },
    "保定西大街": {
        "name": "保定西大街历史文化街区",
        "lng": 115.4885,
        "lat": 38.8558,
        "address": "河北省保定市莲池区西大街",
    },
    "保定军校纪念馆": {
        "name": "保定军校纪念馆",
        "lng": 115.5122,
        "lat": 38.8836,
        "address": "河北省保定市竞秀区东风路",
    },
    "竞秀公园": {
        "name": "竞秀公园",
        "lng": 115.4568,
        "lat": 38.8735,
        "address": "河北省保定市竞秀区",
    },
    "安新": {
        "name": "安新县城",
        "lng": 115.9358,
        "lat": 38.9356,
        "address": "河北省保定市安新县",
    },
    "易县": {
        "name": "易县",
        "lng": 115.4981,
        "lat": 39.3525,
        "address": "河北省保定市易县",
    },
}


def is_route_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _ROUTE_HINT.search(t):
        return True
    if "规划" in t and any(k in t for k in ("保定", "白洋淀", "狼牙山", "旅游", "景点")):
        return True
    return False


def _pick_preset(text: str) -> tuple[str, list[dict]]:
    t = text or ""
    if "狼牙山" in t:
        return "狼牙山", _PRESETS["狼牙山"]
    if "白洋淀" in t:
        return "白洋淀", _PRESETS["白洋淀"]
    return "保定", _PRESETS["保定"]


def _builtin_spot(name: str) -> dict | None:
    """先查行程内置坐标，再查地图 PLACE_LIBRARY。"""
    if name in _SPOT_COORDS:
        meta = _SPOT_COORDS[name]
        return {**meta, "source": "builtin_route"}
    if name in PLACE_LIBRARY:
        meta = PLACE_LIBRARY[name]
        return {
            "name": meta["name"],
            "lng": float(meta["lng"]),
            "lat": float(meta["lat"]),
            "address": meta.get("address") or "",
            "source": "builtin",
        }
    for key, meta in PLACE_LIBRARY.items():
        aliases = {key, meta["name"], *(meta.get("aliases") or [])}
        if name in aliases or any(a in name or name in a for a in aliases if len(a) >= 2):
            return {
                "name": meta["name"],
                "lng": float(meta["lng"]),
                "lat": float(meta["lat"]),
                "address": meta.get("address") or "",
                "source": "builtin",
            }
    return None


def _resolve_spot(name: str, city_hint: str) -> dict:
    """内置坐标优先；再高德实时检索；最后退回城市中心，保证一日游可演示。"""
    builtin = _builtin_spot(name)
    if builtin:
        return builtin

    queries = [name, f"{city_hint}{name}", f"{city_hint}市{name}"]
    last_err = None
    for q in queries:
        try:
            return amap_realtime(q)
        except ValueError as e:
            last_err = e
            continue

    city_pt = _builtin_spot(city_hint)
    if city_pt:
        return {
            "name": name,
            "lng": city_pt["lng"],
            "lat": city_pt["lat"],
            "address": city_pt.get("address") or city_hint,
            "source": "city_fallback",
        }
    raise ValueError(str(last_err) if last_err else f"无法定位：{name}")


def build_day_route(question: str) -> dict:
    """
    返回：
      answer: 带 [[map:]] 标记的 Markdown 行程
      stops: [{order,name,lng,lat,address,slot,tip}]
    """
    city, spots = _pick_preset(question)
    used_amap = False
    used_builtin = False
    lines = [
        f"已为你规划 **{city}一日游** 路线（行程规划工具）。",
        "",
        "按时间顺序游览，右侧地图将依次标记景点：",
        "",
    ]
    stops: list[dict] = []
    for i, spot in enumerate(spots, start=1):
        point = _resolve_spot(spot["name"], city)
        src = point.get("source") or ""
        if src.startswith("amap"):
            used_amap = True
        else:
            used_builtin = True
        stop = {
            "order": i,
            "slot": spot["slot"],
            "name": point["name"],
            "lng": point["lng"],
            "lat": point["lat"],
            "address": point.get("address") or "",
            "tip": spot["tip"],
            "source": src,
        }
        stops.append(stop)
        lines.append(f"### {i}. {spot['slot']} · {stop['name']}")
        lines.append(f"- 看点：{spot['tip']}")
        lines.append(f"- 地址：{stop['address']}")
        lines.append(f"- 坐标：{stop['lng']}, {stop['lat']}")
        lines.append("")
        lines.append(f"[[map:{stop['lng']},{stop['lat']},{stop['name']}]]")
        lines.append("")

    lines.append("---")
    if used_builtin and not used_amap:
        lines.append("说明：当前景点坐标来自内置资料（高德额度紧张时仍可完整演示一日游打点）。")
    elif used_builtin and used_amap:
        lines.append("说明：部分景点为高德实时检索，部分为内置坐标。")
    lines.append("提示：门票/船班以当天景区公告为准；红色场馆请遵守参观秩序。")
    lines.append("可继续追问某一站详情，或说「换成美食向路线」。")

    return {"answer": "\n".join(lines), "stops": stops, "city": city}


def try_build_route(question: str) -> str | None:
    if not is_route_question(question):
        return None
    try:
        return build_day_route(question)["answer"]
    except ValueError as e:
        return (
            f"⚠️ 路线规划部分景点定位失败：{e}\n\n"
            "请稍后再试，或改问「保定一日游 / 白洋淀一日游 / 狼牙山一日游」（内置路线可离线打点）。"
        )
