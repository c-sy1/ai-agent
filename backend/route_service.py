"""行程规划工具：生成一日游建议，并按顺序输出地图打点标记。"""
from __future__ import annotations

import json
import re
import time

import httpx

from llm_config import get_chat_llm_config
from map_service import PLACE_LIBRARY, amap_realtime

_ROUTE_HINT = re.compile(
    r"(一日游|两日游|行程|路线规划|旅游路线|游玩路线|怎么玩|规划.*(游|行程|路线))",
    re.I,
)

# 热门目的地预设（内置坐标，不依赖高德也能打点）
_PRESETS: dict[str, list[dict]] = {
    "保定": [
        {"slot": "上午", "name": "直隶总督署博物馆", "tip": "了解清代直隶政治文化，建议1～1.5小时"},
        {"slot": "上午", "name": "古莲花池", "tip": "古典园林散步拍照，紧邻总督署"},
        {"slot": "中午", "name": "保定西大街", "tip": "午餐+逛历史文化街区"},
        {"slot": "下午", "name": "保定军校纪念馆", "tip": "红色/近代军事史，适合研学"},
        {"slot": "傍晚", "name": "竞秀公园", "tip": "休闲散步收尾，可看夜景"},
    ],
    "北京": [
        {"slot": "上午", "name": "天安门广场", "tip": "升旗/广场拍照，注意安检与预约"},
        {"slot": "上午", "name": "故宫博物院", "tip": "建议提前预约门票，参观2～3小时"},
        {"slot": "中午", "name": "王府井", "tip": "午餐+逛街，可吃北京小吃"},
        {"slot": "下午", "name": "景山公园", "tip": "登顶俯瞰故宫全景"},
        {"slot": "傍晚", "name": "南锣鼓巷", "tip": "胡同氛围收尾，适合散步"},
    ],
    "天津": [
        {"slot": "上午", "name": "天津之眼", "tip": "摩天轮观景，建议先网上购票"},
        {"slot": "上午", "name": "古文化街", "tip": "逛传统街区、买特产小吃"},
        {"slot": "中午", "name": "意式风情区", "tip": "午餐+拍照，欧式建筑集中"},
        {"slot": "下午", "name": "五大道", "tip": "骑行或步行看小洋楼"},
        {"slot": "傍晚", "name": "海河", "tip": "沿岸散步看夜景收尾"},
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

# 预设景点内置坐标（GCJ-02）
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
    "天安门广场": {
        "name": "天安门广场",
        "lng": 116.397477,
        "lat": 39.903739,
        "address": "北京市东城区天安门广场",
    },
    "故宫博物院": {
        "name": "故宫博物院",
        "lng": 116.397026,
        "lat": 39.918058,
        "address": "北京市东城区景山前街4号",
    },
    "王府井": {
        "name": "王府井步行街",
        "lng": 116.418043,
        "lat": 39.914885,
        "address": "北京市东城区王府井大街",
    },
    "景山公园": {
        "name": "景山公园",
        "lng": 116.396715,
        "lat": 39.926072,
        "address": "北京市西城区景山西街44号",
    },
    "南锣鼓巷": {
        "name": "南锣鼓巷",
        "lng": 116.403119,
        "lat": 39.937573,
        "address": "北京市东城区南锣鼓巷",
    },
    "北京": {
        "name": "北京市中心",
        "lng": 116.397128,
        "lat": 39.916527,
        "address": "北京市",
    },
    "天津之眼": {
        "name": "天津之眼摩天轮",
        "lng": 117.1870,
        "lat": 39.1548,
        "address": "天津市红桥区永乐桥",
    },
    "古文化街": {
        "name": "天津古文化街",
        "lng": 117.1905,
        "lat": 39.1462,
        "address": "天津市南开区古文化街",
    },
    "意式风情区": {
        "name": "意大利风情旅游区",
        "lng": 117.2175,
        "lat": 39.1368,
        "address": "天津市河北区自由道",
    },
    "五大道": {
        "name": "五大道风景区",
        "lng": 117.1998,
        "lat": 39.1165,
        "address": "天津市和平区五大道",
    },
    "海河": {
        "name": "海河风光带",
        "lng": 117.2100,
        "lat": 39.1300,
        "address": "天津市海河沿岸",
    },
    "天津": {
        "name": "天津市中心",
        "lng": 117.200983,
        "lat": 39.084158,
        "address": "天津市",
    },
}

# 省名 → 默认按省会做一日游（避免「河南一日游」落到保定）
_PROVINCE_CITY = {
    "河南": "郑州",
    "河北": "石家庄",
    "山西": "太原",
    "山东": "济南",
    "陕西": "西安",
    "四川": "成都",
    "浙江": "杭州",
    "江苏": "南京",
    "湖北": "武汉",
    "湖南": "长沙",
    "广东": "广州",
    "福建": "福州",
    "辽宁": "沈阳",
    "吉林": "长春",
    "黑龙江": "哈尔滨",
    "安徽": "合肥",
    "江西": "南昌",
    "云南": "昆明",
    "贵州": "贵阳",
    "广西": "南宁",
    "海南": "海口",
    "甘肃": "兰州",
    "内蒙古": "呼和浩特",
    "新疆": "乌鲁木齐",
    "西藏": "拉萨",
    "宁夏": "银川",
    "青海": "西宁",
}

_CITY_PAT = re.compile(
    r"(北京|天津|上海|重庆|保定|石家庄|太原|西安|成都|杭州|南京|武汉|广州|深圳|"
    r"苏州|青岛|大连|厦门|长沙|郑州|沈阳|哈尔滨|济南|福州|合肥|南昌|昆明|贵阳|"
    r"南宁|海口|兰州|呼和浩特|乌鲁木齐|拉萨|银川|西宁|白洋淀|狼牙山|"
    + "|".join(map(re.escape, _PROVINCE_CITY.keys()))
    + r"|[\u4e00-\u9fff]{2,8}?(?:市|县|区|州))"
)


def is_route_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _ROUTE_HINT.search(t):
        return True
    if "规划" in t and any(
        k in t for k in ("保定", "白洋淀", "狼牙山", "北京", "天津", "旅游", "景点")
    ):
        return True
    return False


def _extract_city(text: str) -> str | None:
    t = (text or "").strip()
    for key in ("狼牙山", "白洋淀", "北京", "天津", "保定"):
        if key in t:
            return key
    for prov, capital in _PROVINCE_CITY.items():
        if prov in t:
            return capital
    m = _CITY_PAT.search(t)
    if not m:
        return None
    city = m.group(1)
    if city in _PROVINCE_CITY:
        return _PROVINCE_CITY[city]
    city = re.sub(r"(市|县|区|州)$", "", city)
    return city or None


def _pick_preset(text: str) -> tuple[str, list[dict]] | None:
    t = text or ""
    if "狼牙山" in t:
        return "狼牙山", _PRESETS["狼牙山"]
    if "白洋淀" in t:
        return "白洋淀", _PRESETS["白洋淀"]
    if "天津" in t:
        return "天津", _PRESETS["天津"]
    if "北京" in t:
        return "北京", _PRESETS["北京"]
    if "保定" in t:
        return "保定", _PRESETS["保定"]
    # 仅当完全没提任何地名时，才默认保定演示
    stripped = re.sub(r"(一日游|两日游|行程|路线规划|旅游路线|游玩路线|怎么玩|规划|路线|旅游|景点|[？?。！!\s])+", "", t)
    if re.search(r"一日游|行程|路线", t) and len(stripped) < 2:
        return "保定", _PRESETS["保定"]
    return None


def _builtin_spot(name: str) -> dict | None:
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


def _resolve_spot(name: str, city_hint: str, *, allow_amap: bool = True) -> dict:
    """内置优先；可选高德；最后退回城市中心。"""
    builtin = _builtin_spot(name)
    if builtin:
        return builtin

    last_err = None
    if allow_amap:
        queries = [name, f"{city_hint}{name}", f"{city_hint}市{name}"]
        for q in queries:
            try:
                time.sleep(0.35)  # 降低并发，减少个人开发者 QPS 超限
                return amap_realtime(q)
            except ValueError as e:
                last_err = e
                continue

    city_pt = _builtin_spot(city_hint)
    if not city_pt and allow_amap:
        try:
            time.sleep(0.35)
            city_pt = amap_realtime(city_hint)
        except ValueError as e:
            last_err = e
    if city_pt:
        return {
            "name": name,
            "lng": float(city_pt["lng"]),
            "lat": float(city_pt["lat"]),
            "address": city_pt.get("address") or city_hint,
            "source": "city_fallback",
        }
    raise ValueError(str(last_err) if last_err else f"无法定位：{name}")


def _llm_spots_for_city(city: str) -> list[dict]:
    """无预设时用大模型生成一日游站点列表。"""
    cfg = get_chat_llm_config()
    if not cfg:
        raise ValueError("未配置对话模型，无法为新城市生成行程。请先配置 ZHIPU_API_KEY。")

    prompt = (
        f"请为「{city}」规划经典一日游，输出严格 JSON 数组，不要 Markdown。"
        '每项字段：slot(上午/中午/下午/傍晚), name(景点名), tip(一句话看点)。'
        "共 4～5 个点，按游览顺序，景点名要真实可检索。"
    )
    with httpx.Client(timeout=httpx.Timeout(30.0, read=60.0)) as client:
        resp = client.post(
            f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}"},
            json={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": "你只输出 JSON 数组，不要解释。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content") or ""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        raise ValueError("模型未返回有效行程列表")

    spots: list[dict] = []
    for item in data[:5]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        spots.append(
            {
                "slot": str(item.get("slot") or "全天").strip() or "全天",
                "name": name,
                "tip": str(item.get("tip") or "建议按现场开放时间参观").strip(),
            }
        )
    if len(spots) < 2:
        raise ValueError("生成的行程景点过少，请换个城市再试")
    return spots


def _format_route(
    city: str,
    spots: list[dict],
    *,
    dynamic: bool = False,
) -> dict:
    used_amap = False
    used_builtin = False
    failed: list[str] = []
    lines = [
        f"已为你规划 **{city}一日游** 路线（行程规划工具）。",
        "",
        "按时间顺序游览，右侧地图将依次标记景点：",
        "",
    ]
    stops: list[dict] = []
    for i, spot in enumerate(spots, start=1):
        try:
            point = _resolve_spot(spot["name"], city, allow_amap=True)
        except ValueError:
            failed.append(spot["name"])
            continue
        src = point.get("source") or ""
        if src.startswith("amap") or src == "city_fallback":
            used_amap = True
        else:
            used_builtin = True
        stop = {
            "order": len(stops) + 1,
            "slot": spot["slot"],
            "name": point["name"],
            "lng": point["lng"],
            "lat": point["lat"],
            "address": point.get("address") or "",
            "tip": spot["tip"],
            "source": src,
        }
        stops.append(stop)
        n = stop["order"]
        lines.append(f"### {n}. {spot['slot']} · {stop['name']}")
        lines.append(f"- 看点：{spot['tip']}")
        lines.append(f"- 地址：{stop['address']}")
        lines.append(f"- 坐标：{stop['lng']}, {stop['lat']}")
        lines.append("")
        lines.append(f"[[map:{stop['lng']},{stop['lat']},{stop['name']}]]")
        lines.append("")

    if not stops:
        raise ValueError(
            "景点定位全部失败（高德可能超限）。"
            f"可先试内置城市：{'、'.join(_PRESETS.keys())}。"
        )

    lines.append("---")
    if dynamic:
        lines.append("说明：该城市无固定模板，行程由 AI 生成，坐标尽量实时检索。")
    if used_builtin and not used_amap:
        lines.append("说明：当前景点坐标来自内置资料（高德额度紧张时仍可完整演示）。")
    elif used_builtin and used_amap:
        lines.append("说明：部分景点为高德实时检索，部分为内置坐标。")
    if failed:
        lines.append(f"说明：以下景点暂未能定位，已跳过：{'、'.join(failed)}。")
    lines.append("提示：门票/开放时间以当天景区公告为准。")
    lines.append("可继续追问某一站详情，或换其他城市再规划。")

    return {"answer": "\n".join(lines), "stops": stops, "city": city}


def build_day_route(question: str) -> dict:
    """
    返回：
      answer: 带 [[map:]] 标记的 Markdown 行程
      stops: [{order,name,lng,lat,address,slot,tip}]
    """
    picked = _pick_preset(question)
    if picked:
        city, spots = picked
        return _format_route(city, spots, dynamic=False)

    city = _extract_city(question)
    if not city:
        raise ValueError(
            "请说明城市，例如「天津一日游」「上海一日游」。"
            f"内置稳定路线：{'、'.join(_PRESETS.keys())}。"
        )

    spots = _llm_spots_for_city(city)
    return _format_route(city, spots, dynamic=True)


def try_build_route(question: str) -> str | None:
    if not is_route_question(question):
        return None
    try:
        return build_day_route(question)["answer"]
    except Exception as e:
        return (
            f"⚠️ 路线规划暂时失败：{e}\n\n"
            f"可先试内置城市：{' / '.join(_PRESETS.keys())}；"
            "其他城市需对话模型 + 高德检索，额度恢复后再试。"
        )
