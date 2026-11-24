"""行程规划工具：生成一日游建议，并按顺序输出地图打点标记。"""
from __future__ import annotations

import re

from map_service import amap_realtime

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


def _resolve_spot(name: str, city_hint: str) -> dict:
    """实时检索景点坐标；失败则退回城市中心附近提示。"""
    queries = [name, f"{city_hint}{name}", f"{city_hint}市{name}"]
    last_err = None
    for q in queries:
        try:
            return amap_realtime(q)
        except ValueError as e:
            last_err = e
            continue
    raise ValueError(str(last_err) if last_err else f"无法定位：{name}")


def build_day_route(question: str) -> dict:
    """
    返回：
      answer: 带 [[map:]] 标记的 Markdown 行程
      stops: [{order,name,lng,lat,address,slot,tip}]
    """
    city, spots = _pick_preset(question)
    lines = [
        f"已为你规划 **{city}一日游** 路线（行程规划工具）。",
        "",
        "按时间顺序游览，右侧地图将依次标记景点：",
        "",
    ]
    stops: list[dict] = []
    for i, spot in enumerate(spots, start=1):
        point = _resolve_spot(spot["name"], city)
        stop = {
            "order": i,
            "slot": spot["slot"],
            "name": point["name"],
            "lng": point["lng"],
            "lat": point["lat"],
            "address": point.get("address") or "",
            "tip": spot["tip"],
            "source": point.get("source"),
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
            "请确认已配置 AMAP_WEB_KEY，或换个目的地再试（如：保定一日游）。"
        )
