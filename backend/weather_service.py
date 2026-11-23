"""实时天气：Open-Meteo（免费、无需 Key）。"""
from __future__ import annotations

import re
from typing import Optional

import httpx

_CITY_MAP = {
    "北京": "Beijing",
    "上海": "Shanghai",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "杭州": "Hangzhou",
    "成都": "Chengdu",
    "重庆": "Chongqing",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "南京": "Nanjing",
    "苏州": "Suzhou",
    "天津": "Tianjin",
    "长沙": "Changsha",
    "郑州": "Zhengzhou",
    "青岛": "Qingdao",
    "大连": "Dalian",
    "厦门": "Xiamen",
    "福州": "Fuzhou",
    "合肥": "Hefei",
    "济南": "Jinan",
    "沈阳": "Shenyang",
    "哈尔滨": "Harbin",
    "昆明": "Kunming",
    "贵阳": "Guiyang",
    "南宁": "Nanning",
    "海口": "Haikou",
    "三亚": "Sanya",
    "兰州": "Lanzhou",
    "乌鲁木齐": "Urumqi",
    "呼和浩特": "Hohhot",
    "银川": "Yinchuan",
    "西宁": "Xining",
    "拉萨": "Lhasa",
    "香港": "Hong Kong",
    "澳门": "Macau",
    "台北": "Taipei",
}

_WMO = {
    0: "晴",
    1: "主要晴朗",
    2: "少云",
    3: "多云",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "强雷暴冰雹",
}

_WEATHER_RE = re.compile(
    r"(天气|气温|温度|下雨|下雪|多少度|冷不冷|热不热|穿什么.*(天|气)|天气预报)",
    re.I,
)


def is_weather_question(text: str) -> bool:
    return bool(_WEATHER_RE.search(text or ""))


def _extract_city(text: str) -> str:
    t = text or ""
    for zh in sorted(_CITY_MAP.keys(), key=len, reverse=True):
        if zh in t:
            return zh
    m = re.search(r"([\u4e00-\u9fff]{2,8})(?:的)?(?:天气|气温|温度)", t)
    if m:
        city = m.group(1)
        for noise in ("今天", "明天", "后天", "现在", "本地", "请问", "一下", "怎么样"):
            city = city.replace(noise, "")
        if city:
            return city
    return "北京"


def _geocode(city_zh: str) -> Optional[tuple[str, float, float]]:
    name = _CITY_MAP.get(city_zh, city_zh)
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": name, "count": 1, "language": "zh", "format": "json"},
            )
            r.raise_for_status()
            results = (r.json() or {}).get("results") or []
            if not results:
                return None
            hit = results[0]
            label = hit.get("name") or city_zh
            admin = hit.get("admin1") or ""
            country = hit.get("country") or ""
            show = f"{label}"
            if admin and admin != label:
                show += f"（{admin}）"
            if country:
                show += f" · {country}"
            return show, float(hit["latitude"]), float(hit["longitude"])
    except Exception:
        return None


def fetch_weather(question: str) -> str:
    city_zh = _extract_city(question)
    geo = _geocode(city_zh)
    if not geo:
        return (
            f"没找到「{city_zh}」的位置信息。你可以写成「北京天气」「上海今天气温」再试一次。"
        )
    label, lat, lon = geo
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 3,
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        return f"天气服务暂时不可用（{type(e).__name__}），请稍后再试。"

    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(cur.get("weather_code") or 0)
    desc = _WMO.get(code, f"天气代码 {code}")
    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    hum = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")

    lines = [
        f"【实时天气 · {label}】",
        f"当前：{desc}，气温 {temp}℃（体感 {feels}℃）",
        f"湿度 {hum}% · 风速 {wind} km/h",
        "",
        "近 3 天：",
    ]
    dates = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    pop = daily.get("precipitation_probability_max") or []
    for i, d in enumerate(dates[:3]):
        hi = tmax[i] if i < len(tmax) else "-"
        lo = tmin[i] if i < len(tmin) else "-"
        p = pop[i] if i < len(pop) else "-"
        lines.append(f"- {d}：{lo}～{hi}℃，降水概率 {p}%")

    lines.append("")
    lines.append("数据来源：Open-Meteo（实时，无需配置 Key）")
    if "穿" in (question or ""):
        t = float(temp) if temp is not None else 20
        if t >= 28:
            tip = "天气偏热，建议短袖透气衣物，注意防晒。"
        elif t >= 20:
            tip = "温度舒适，衬衫/薄外套即可。"
        elif t >= 10:
            tip = "略凉，建议长袖 + 薄外套。"
        else:
            tip = "较冷，建议厚外套或羽绒服。"
        lines.append(f"穿衣建议：{tip}")
    return "\n".join(lines)
