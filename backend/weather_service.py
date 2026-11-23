"""实时天气：优先 wttr.in，失败再试 Open-Meteo（适配国内服务器出网限制）。"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

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
    "西安": "Xian",
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
    "香港": "HongKong",
    "澳门": "Macau",
    "台北": "Taipei",
}

# 常用城市坐标（避免再请求国外地理编码）
_CITY_COORDS = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551),
    "成都": (30.5728, 104.0668),
    "重庆": (29.5630, 106.5516),
    "武汉": (30.5928, 114.3055),
    "西安": (34.3416, 108.9398),
    "南京": (32.0603, 118.7969),
    "苏州": (31.2989, 120.5853),
    "天津": (39.3434, 117.3616),
    "长沙": (28.2282, 112.9388),
    "郑州": (34.7466, 113.6253),
    "青岛": (36.0671, 120.3826),
    "大连": (38.9140, 121.6147),
    "厦门": (24.4798, 118.0894),
    "福州": (26.0745, 119.2965),
    "合肥": (31.8206, 117.2272),
    "济南": (36.6512, 117.1201),
    "沈阳": (41.8057, 123.4315),
    "哈尔滨": (45.8038, 126.5349),
    "昆明": (25.0389, 102.7183),
    "贵阳": (26.6470, 106.6302),
    "南宁": (22.8170, 108.3669),
    "海口": (20.0440, 110.1999),
    "三亚": (18.2528, 109.5119),
    "兰州": (36.0611, 103.8343),
    "乌鲁木齐": (43.8256, 87.6168),
    "呼和浩特": (40.8424, 111.7492),
    "银川": (38.4872, 106.2309),
    "西宁": (36.6171, 101.7782),
    "拉萨": (29.6525, 91.1721),
    "香港": (22.3193, 114.1694),
    "澳门": (22.1987, 113.5439),
    "台北": (25.0330, 121.5654),
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

_TIMEOUT = httpx.Timeout(8.0, connect=5.0)


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


def _dress_tip(temp: Optional[float], question: str) -> str:
    if "穿" not in (question or ""):
        return ""
    t = float(temp) if temp is not None else 20.0
    if t >= 28:
        tip = "天气偏热，建议短袖透气衣物，注意防晒。"
    elif t >= 20:
        tip = "温度舒适，衬衫/薄外套即可。"
    elif t >= 10:
        tip = "略凉，建议长袖 + 薄外套。"
    else:
        tip = "较冷，建议厚外套或羽绒服。"
    return f"\n穿衣建议：{tip}"


def _from_wttr(city_zh: str, question: str) -> Optional[str]:
    en = _CITY_MAP.get(city_zh, city_zh)
    # 先英文城市名，再试中文
    for query in (en, city_zh):
        url = f"https://wttr.in/{quote(query)}?format=j1"
        try:
            with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
                r = client.get(url, headers={"User-Agent": "ApexAI/1.0"})
                r.raise_for_status()
                data = r.json()
        except Exception:
            continue
        cur = (data.get("current_condition") or [{}])[0]
        nearest = ((data.get("nearest_area") or [{}])[0].get("areaName") or [{}])[0]
        area = nearest.get("value") or city_zh
        desc = (cur.get("lang_zh") or cur.get("weatherDesc") or [{}])[0].get("value") or "-"
        temp = cur.get("temp_C")
        feels = cur.get("FeelsLikeC")
        hum = cur.get("humidity")
        wind = cur.get("windspeedKmph")
        lines = [
            f"【实时天气 · {area}】",
            f"当前：{desc}，气温 {temp}℃（体感 {feels}℃）",
            f"湿度 {hum}% · 风速 {wind} km/h",
            "",
            "近几日：",
        ]
        for day in (data.get("weather") or [])[:3]:
            d = day.get("date") or "-"
            mi = day.get("mintempC")
            ma = day.get("maxtempC")
            lines.append(f"- {d}：{mi}～{ma}℃")
        lines.append("")
        lines.append("数据来源：wttr.in")
        text = "\n".join(lines) + _dress_tip(
            float(temp) if temp not in (None, "") else None, question
        )
        return text
    return None


def _from_open_meteo(city_zh: str, question: str) -> Optional[str]:
    coords = _CITY_COORDS.get(city_zh)
    if not coords:
        return None
    lat, lon = coords
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "Asia/Shanghai",
                    "forecast_days": 3,
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(cur.get("weather_code") or 0)
    desc = _WMO.get(code, f"天气代码 {code}")
    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    hum = cur.get("relative_humidity_2m")
    wind = cur.get("wind_speed_10m")
    lines = [
        f"【实时天气 · {city_zh}】",
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
    lines.append("数据来源：Open-Meteo")
    return "\n".join(lines) + _dress_tip(
        float(temp) if temp is not None else None, question
    )


def fetch_weather(question: str) -> str:
    city_zh = _extract_city(question)
    # 国内云主机访问国外接口常超时：先 wttr，再 Open-Meteo
    for getter in (_from_wttr, _from_open_meteo):
        try:
            text = getter(city_zh, question)
            if text:
                return text
        except Exception:
            continue
    return (
        f"天气服务暂时连不上（服务器访问外网天气接口超时）。\n"
        f"已尝试查询：{city_zh}。请稍后重试，或换具体城市如「上海天气」。"
    )
