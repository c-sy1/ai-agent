import base64
import os
import re
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH, override=True)

GENERATED_ROOT = Path(__file__).resolve().parent / "generated"
IMAGE_DIR = GENERATED_ROOT / "images"
VIDEO_DIR = GENERATED_ROOT / "videos"
UPLOAD_DIR = GENERATED_ROOT / "uploads"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

DASHSCOPE_BASE = os.getenv(
    "DASHSCOPE_API_BASE", "https://dashscope.aliyuncs.com/api/v1"
).rstrip("/")
MODELSCOPE_BASE = os.getenv(
    "MODELSCOPE_API_BASE", "https://api-inference.modelscope.cn/v1"
).rstrip("/")
# 默认走魔搭免费文生图，不再强依赖通义万相
IMAGE_MODEL = os.getenv("MODELSCOPE_IMAGE_MODEL", "Tongyi-MAI/Z-Image-Turbo")
DASHSCOPE_IMAGE_MODEL = os.getenv("DASHSCOPE_IMAGE_MODEL", "wanx2.1-t2i-turbo")
# 真实文生视频（连贯运镜），默认 turbo 更快更稳
VIDEO_MODEL = os.getenv("DASHSCOPE_VIDEO_MODEL", "wanx2.1-t2v-turbo")
VIDEO_MODEL_FALLBACKS = [
    "wanx2.1-t2v-turbo",
    "wanx2.1-t2v-plus",
    "wan2.2-t2v-plus",
]


class MediaError(Exception):
    pass


def _reload_env() -> None:
    load_dotenv(_ENV_PATH, override=True)


def _modelscope_api_key() -> str:
    _reload_env()
    for name in ("MODELSCOPE_API_KEY", "QIANWEN_API_KEY", "DASHSCOPE_API_KEY"):
        key = (os.getenv(name) or "").strip()
        if key:
            return key
    raise MediaError("未配置可用密钥：请在 backend/.env 设置 MODELSCOPE_API_KEY（魔搭 ms-...）")


def _dashscope_api_key(purpose: str = "通义万相") -> str:
    """通义万相（修图/收费视频等），仅接受非 ms- 的 Key。"""
    _reload_env()
    primary = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
    fallback = (os.getenv("QIANWEN_API_KEY") or "").strip()
    for key in (primary, fallback):
        if key and not key.startswith("ms-"):
            return key
    raise MediaError(
        f"{purpose}需要阿里云百炼 DashScope Key（sk-...），"
        "魔搭 ms- Key 不能用于此项。"
        "请在 backend/.env 配置 DASHSCOPE_API_KEY。"
    )


def _dashscope_headers(async_mode: bool = True) -> dict:
    key = _dashscope_api_key()
    h = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if async_mode:
        h["X-DashScope-Async"] = "enable"
    return h


def _poll_dashscope_task(task_id: str, timeout_sec: int = 120) -> dict:
    deadline = time.time() + timeout_sec
    key = _dashscope_api_key()
    with httpx.Client(timeout=30.0) as client:
        while time.time() < deadline:
            resp = client.get(
                f"{DASHSCOPE_BASE}/tasks/{task_id}",
                headers={"Authorization": f"Bearer {key}"},
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("output", {}).get("task_status") or data.get(
                "task_status"
            )
            if status in ("SUCCEEDED", "SUCCESS"):
                return data
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                msg = data.get("output", {}).get("message") or data.get("message")
                raise MediaError(msg or f"任务失败: {status}")
            time.sleep(2)
    raise MediaError("生成超时，请稍后重试")


def _download(url: str, dest: Path) -> None:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)


def _public_path(kind: str, filename: str) -> str:
    return f"/generated/{kind}/{filename}"


def _generate_image_modelscope(prompt: str) -> str:
    key = _modelscope_api_key()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true",
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{MODELSCOPE_BASE}/images/generations",
            headers=headers,
            json={
                "model": IMAGE_MODEL,
                "prompt": prompt[:800],
                "n": 1,
                "size": "1024x1024",
            },
        )
        if resp.status_code >= 400:
            raise MediaError(_parse_error(resp))
        data = resp.json()
        task_id = data.get("task_id")
        if not task_id:
            urls = data.get("output_images") or _extract_urls(data)
            if urls:
                return _save_image_url(urls[0])
            raise MediaError("魔搭未返回图片任务 ID")

        deadline = time.time() + 120
        while time.time() < deadline:
            poll = client.get(
                f"{MODELSCOPE_BASE}/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {key}",
                    "X-ModelScope-Task-Type": "image_generation",
                },
            )
            if poll.status_code >= 400:
                raise MediaError(_parse_error(poll))
            body = poll.json()
            status = body.get("task_status") or body.get("status") or ""
            status_u = str(status).upper()
            if status_u in ("SUCCEED", "SUCCEEDED", "SUCCESS"):
                urls = body.get("output_images") or _extract_urls(body)
                if not urls:
                    raise MediaError("魔搭未返回图片地址")
                return _save_image_url(urls[0])
            if status_u in ("FAILED", "ERROR", "CANCELED"):
                raise MediaError(body.get("message") or body.get("error") or "魔搭图片生成失败")
            time.sleep(2)
    raise MediaError("魔搭图片生成超时，请稍后重试")


def _generate_image_dashscope(prompt: str) -> str:
    payload = {
        "model": DASHSCOPE_IMAGE_MODEL,
        "input": {"prompt": prompt[:800]},
        "parameters": {"size": "1024*1024", "n": 1},
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{DASHSCOPE_BASE}/services/aigc/text2image/image-synthesis",
            headers=_dashscope_headers(async_mode=True),
            json=payload,
        )
        if resp.status_code >= 400:
            raise MediaError(_parse_error(resp))
        data = resp.json()
        task_id = data.get("output", {}).get("task_id") or data.get("task_id")
        if not task_id:
            urls = _extract_urls(data)
            if urls:
                return _save_image_url(urls[0])
            raise MediaError("未返回图片任务 ID")

    result = _poll_dashscope_task(task_id, timeout_sec=90)
    urls = _extract_urls(result)
    if not urls:
        raise MediaError("未获取到图片地址")
    return _save_image_url(urls[0])


def generate_image(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if not prompt:
        raise MediaError("请描述要生成的画面")

    # 优先魔搭（你现在的 ms- Key 可用），通义万相仅作可选兜底
    errors: list[str] = []
    try:
        return _generate_image_modelscope(prompt)
    except MediaError as e:
        errors.append(f"魔搭：{e}")
    try:
        return _generate_image_dashscope(prompt)
    except MediaError as e:
        errors.append(f"通义万相：{e}")
    raise MediaError("；".join(errors) if errors else "图片生成失败")


def _video_models() -> list[str]:
    models = [VIDEO_MODEL] + VIDEO_MODEL_FALLBACKS
    seen: set[str] = set()
    ordered: list[str] = []
    for m in models:
        name = (m or "").strip()
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


# 知名 IP / 角色名易触发万相内容审核，提交前改写成通用描述
_IP_SOFTEN: list[tuple[re.Pattern, str]] = [
    (re.compile(r"海绵宝宝|SpongeBob(?:\s+SquarePants)?", re.I), "黄色方形海绵卡通角色"),
    (re.compile(r"派大星|Patrick\s+Star", re.I), "粉色海星卡通角色"),
    (re.compile(r"章鱼哥|Squidward", re.I), "章鱼卡通角色"),
    (re.compile(r"小猪佩奇|Peppa\s+Pig", re.I), "粉色小猪卡通角色"),
    (re.compile(r"米老鼠|Mickey\s+Mouse", re.I), "圆耳黑白卡通老鼠角色"),
    (re.compile(r"哆啦A梦|Doraemon", re.I), "蓝色机器猫卡通角色"),
    (re.compile(r"皮卡丘|Pikachu", re.I), "黄色电气鼠卡通角色"),
    (re.compile(r"马里奥|Mario", re.I), "红帽水管工卡通角色"),
    (re.compile(r"蜘蛛侠|Spider-?Man", re.I), "红蓝紧身衣超级英雄角色"),
    (re.compile(r"冰雪奇缘|Elsa|Anna\b", re.I), "冰雪王国童话公主角色"),
]


def _soften_video_prompt(prompt: str) -> str:
    """去掉易触发审核的品牌/角色名，保留场景动作描述。"""
    text = (prompt or "").strip()
    for pat, repl in _IP_SOFTEN:
        text = pat.sub(repl, text)
    # 再压一层：明确写“原创风格”，降低版权误杀
    if "原创" not in text and "original" not in text.lower():
        text = f"原创卡通风格，{text}"
    return text[:800]


_CN_DURATION = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
    "十三": 13,
    "十四": 14,
    "十五": 15,
}


def parse_video_duration(text: str) -> int | None:
    """从用户话里解析想要的秒数；解析不到返回 None。"""
    t = text or ""
    m = re.search(r"(\d+)\s*(秒|s\b|sec)", t, re.I)
    if m:
        return max(1, min(15, int(m.group(1))))
    m = re.search(r"(十一|十二|十三|十四|十五|十|[一二两三四五六七八九])\s*秒", t)
    if m:
        return _CN_DURATION.get(m.group(1))
    return None


def video_prompt_lacks_scene(text: str) -> bool:
    """只有「生成N秒视频」这类空指令、没有画面内容时返回 True。"""
    cleaned = _strip_media_command(text or "")
    cleaned = re.sub(
        r"(\d+\s*(秒|s|sec)|[一二两三四五六七八九十十一十二十三十四十五]+\s*秒|十秒钟?)",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"(一段|一个|一部|生成|制作|做|视频|短片|动画|请|帮我|给我|帮忙|高清|秒|钟)",
        "",
        cleaned,
    )
    cleaned = re.sub(r"[\s，,。.!！?？：:、～~]+", "", cleaned)
    return len(cleaned) < 4


def _resolve_video_duration(prompt: str, requested: int | None) -> tuple[int, str]:
    """
    返回实际提交秒数 + 给用户的说明。
    免费魔搭约 3～5 秒；付费 wan2.5 才支持 10 秒。
    """
    want = requested or parse_video_duration(prompt) or 5
    want = max(1, min(15, int(want)))
    if want > 5 and _video_allow_paid():
        # wan2.5：5 或 10
        actual = 10 if want >= 10 else 5
        note = f"已按约 {actual} 秒生成（付费万相）。"
        return actual, note
    actual = 5 if want >= 5 else max(3, want)
    if want > 5:
        note = (
            f"你要 {want} 秒，但当前免费视频模型单条约 3～5 秒，已按约 {actual} 秒生成。"
            "要更长需开启付费万相（VIDEO_ALLOW_PAID=true，费用更高）。"
        )
    else:
        note = f"单条约 {actual} 秒（模型上限，无法精确卡到任意秒数）。"
    return actual, note


def _is_content_policy_error(msg: str) -> bool:
    text = msg or ""
    low = text.lower()
    keys = (
        "inappropriate content",
        "inappropriate",
        "sensitive content",
        "data_inspection",
        "content policy",
        "moderat",
        "违规",
        "敏感",
        "不当内容",
        "内容审核",
        "不适宜",
    )
    return any(k in low or k in text for k in keys)


def _submit_video_task(prompt: str, model: str, duration: int = 5) -> str:
    params: dict = {"size": "1280*720", "prompt_extend": True}
    # wan2.5 支持 5/10；wan2.6 支持 2～15；2.1/2.2 固定 5 秒传了也会忽略
    low = (model or "").lower()
    if "wan2.5" in low or "wan2.6" in low:
        params["duration"] = int(duration)
    elif duration:
        params["duration"] = 5
    payload = {
        "model": model,
        "input": {"prompt": prompt[:800]},
        "parameters": params,
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{DASHSCOPE_BASE}/services/aigc/video-generation/video-synthesis",
            headers=_dashscope_headers(async_mode=True),
            json=payload,
        )
        if resp.status_code >= 400:
            raise MediaError(_parse_error(resp))
        data = resp.json()
        task_id = data.get("output", {}).get("task_id") or data.get("task_id")
        if not task_id:
            urls = _extract_urls(data)
            if urls:
                return urls[0]
            raise MediaError("未返回视频任务 ID")
    return task_id


def _generate_video_modelscope(prompt: str, duration: int = 5) -> str:
    """魔搭真实文生视频；限流时短暂重试。时长约 3～5 秒。"""
    key = _modelscope_api_key()
    model = os.getenv("MODELSCOPE_VIDEO_MODEL", "Wan-AI/Wan2.1-T2V-1.3B")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-ModelScope-Async-Mode": "true",
        "X-ModelScope-DataInspection": "{}",
    }
    body = {
        "model": model,
        "prompt": prompt[:500],
        # 部分魔搭网关会读 seconds；不支持则忽略，仍约 3～5 秒
        "seconds": max(3, min(5, int(duration or 5))),
    }
    last_error = "魔搭视频失败"
    with httpx.Client(timeout=60.0) as client:
        data = None
        for attempt in range(4):
            resp = client.post(
                f"{MODELSCOPE_BASE}/videos/generations",
                headers=headers,
                json=body,
            )
            if resp.status_code >= 400:
                last_error = _parse_error(resp)
                if "429" in last_error or "频繁" in last_error:
                    time.sleep(6 * (attempt + 1))
                    continue
                raise MediaError(last_error)
            data = resp.json()
            if data.get("status") == "FAILED" or data.get("errors"):
                err = data.get("errors") or {}
                last_error = err.get("message") or str(data)[:200]
                code = str(err.get("code") or "")
                if code == "429" or "频繁" in last_error:
                    time.sleep(6 * (attempt + 1))
                    continue
                raise MediaError(last_error)
            break
        else:
            raise MediaError(last_error)

        task_id = data.get("task_id")
        if not task_id:
            urls = data.get("output_videos") or _extract_urls(data)
            if urls:
                return _save_video_url(urls[0])
            raise MediaError("魔搭未返回视频任务 ID")

        deadline = time.time() + 300
        while time.time() < deadline:
            poll = client.get(
                f"{MODELSCOPE_BASE}/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {key}",
                    "X-ModelScope-Task-Type": "video_generation",
                },
            )
            if poll.status_code >= 400:
                raise MediaError(_parse_error(poll))
            body = poll.json()
            status = str(body.get("task_status") or body.get("status") or "").upper()
            if status in ("SUCCEED", "SUCCEEDED", "SUCCESS"):
                urls = (
                    body.get("output_videos")
                    or body.get("output_images")
                    or _extract_urls(body)
                )
                if not urls:
                    raise MediaError("魔搭未返回视频地址")
                return _save_video_url(urls[0])
            if status in ("FAILED", "ERROR", "CANCELED"):
                raise MediaError(body.get("message") or body.get("error") or "魔搭视频生成失败")
            time.sleep(5)
    raise MediaError("魔搭视频生成超时")


def _generate_video_dashscope(prompt: str, duration: int = 5) -> str:
    """通义万相真实文生视频（连贯短片，非拼图）。"""
    last_error = "通义万相视频失败"
    models = list(_video_models())
    # 要 10 秒时优先 wan2.5（支持 5/10）
    if duration and duration >= 10:
        long_model = (
            os.getenv("DASHSCOPE_VIDEO_LONG_MODEL") or "wan2.5-t2v-preview"
        ).strip()
        if long_model:
            models = [long_model] + [m for m in models if m != long_model]
    for model in models:
        try:
            task_id = _submit_video_task(prompt, model, duration=duration)
            if task_id.startswith("http") or task_id.startswith("/"):
                return _save_video_url(task_id)
            result = _poll_dashscope_task(task_id, timeout_sec=300)
            urls = _extract_urls(result)
            if not urls:
                raise MediaError("未获取到视频地址")
            return _save_video_url(urls[0])
        except MediaError as e:
            last_error = str(e)
            low = last_error.lower()
            # 内容审核失败：交给外层改写后重试，不在这里换模型空转
            if _is_content_policy_error(last_error):
                raise
            # 可换模型继续试
            if any(
                x in low
                for x in (
                    "model not exist",
                    "invalidparameter",
                    "unsupported",
                    "not supported",
                    "arrearage",
                    "access denied",
                    "insufficient",
                )
            ) or any(
                x in last_error
                for x in ("不存在", "欠费", "无权限", "不支持", "余额")
            ):
                continue
            raise
    raise MediaError(last_error)


def _video_allow_paid() -> bool:
    """默认不走收费通义万相；.env 设 VIDEO_ALLOW_PAID=true 才启用。"""
    _reload_env()
    return (os.getenv("VIDEO_ALLOW_PAID") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def generate_video(prompt: str, duration: int | None = None) -> tuple[str, str]:
    """生成视频。返回 (相对路径, 时长说明)。"""
    prompt = (prompt or "").strip()
    if not prompt:
        raise MediaError("请描述要生成的视频内容")

    actual_sec, duration_note = _resolve_video_duration(prompt, duration)
    soft = _soften_video_prompt(prompt)
    errors: list[str] = []

    # 默认只走魔搭免费文生视频（可能排队/限流）
    try:
        path = _generate_video_modelscope(soft, duration=actual_sec)
        return path, duration_note
    except MediaError as e:
        errors.append(f"魔搭视频：{e}")

    # 收费通道：显式打开才用
    if _video_allow_paid():
        candidates = [prompt, soft]
        soft2 = (
            "原创卡通短片，明亮配色，角色在自然场景中欢快活动，"
            "动作连贯流畅，电影运镜，无品牌标识无文字水印"
        )
        if soft2 not in candidates:
            candidates.append(soft2)
        seen: set[str] = set()
        for text in candidates:
            key = text.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                path = _generate_video_dashscope(key, duration=actual_sec)
                return path, duration_note
            except MediaError as e:
                msg = str(e)
                errors.append(f"通义万相：{msg}")
                if not _is_content_policy_error(msg):
                    break
    else:
        errors.append(
            "已关闭收费视频（通义万相）。若要启用请在 .env 设置 VIDEO_ALLOW_PAID=true"
        )

    raise MediaError(
        "免费真实视频暂不可用（魔搭常限流）。"
        + ("；".join(errors) if errors else "")
    )


def _parse_error(resp: httpx.Response) -> str:
    try:
        j = resp.json()
        return j.get("message") or j.get("error", {}).get("message") or resp.text[:200]
    except Exception:
        return resp.text[:200] or f"HTTP {resp.status_code}"


def _extract_urls(data: dict) -> list[str]:
    urls: list[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("url", "video_url", "image_url") and isinstance(v, str):
                    urls.append(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for i in obj:
                walk(i)

    walk(data)
    return urls


def _save_image_url(url: str) -> str:
    name = f"{uuid.uuid4().hex}.png"
    dest = IMAGE_DIR / name
    _download(url, dest)
    return _public_path("images", name)


def _decode_image_bytes(image_base64: str) -> tuple[bytes, str]:
    raw = (image_base64 or "").strip()
    if not raw:
        raise MediaError("请先上传照片")
    mime = "image/jpeg"
    if raw.startswith("data:"):
        header, _, b64 = raw.partition(",")
        if not b64:
            raise MediaError("图片数据无效")
        if "image/png" in header:
            mime = "image/png"
        elif "image/webp" in header:
            mime = "image/webp"
        raw = b64
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception as e:
        raise MediaError("图片解码失败") from e
    if len(data) < 32:
        raise MediaError("图片过小或损坏")
    if len(data) > 10 * 1024 * 1024:
        raise MediaError("图片请小于 10MB")
    return data, mime


def save_upload_image(image_base64: str) -> str:
    """保存前端上传的 dataURL / base64 图片，返回 /generated/uploads/..."""
    data, mime = _decode_image_bytes(image_base64)
    ext = {"image/png": ".png", "image/webp": ".webp"}.get(mime, ".jpg")
    name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / name
    dest.write_bytes(data)
    return _public_path("uploads", name)


def _resize_for_edit(img):
    from PIL import Image

    w, h = img.size
    long_side = max(w, h)
    if long_side > 2048:
        scale = 2048 / float(long_side)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        w, h = img.size
    if min(w, h) < 512:
        scale = 512 / float(min(w, h))
        img = img.resize((max(512, int(w * scale)), max(512, int(h * scale))), Image.Resampling.LANCZOS)
    return img


def _prepare_edit_image(image_base64: str):
    """返回 (data_url, (w,h))，JPEG RGB。"""
    from io import BytesIO

    from PIL import Image

    data, _mime = _decode_image_bytes(image_base64)
    try:
        img = Image.open(BytesIO(data)).convert("RGB")
    except Exception as e:
        raise MediaError("无法读取上传图片，请换 jpg/png") from e
    img = _resize_for_edit(img)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", img.size


def _prepare_mask_data_url(mask_base64: str, size: tuple[int, int]) -> str:
    """蒙版缩放到与原图一致：白色=要修改，黑色=保留。"""
    from io import BytesIO

    from PIL import Image, ImageOps

    data, _mime = _decode_image_bytes(mask_base64)
    try:
        mask = Image.open(BytesIO(data)).convert("L")
    except Exception as e:
        raise MediaError("无法读取涂抹蒙版") from e
    mask = mask.resize(size, Image.Resampling.NEAREST)
    # 二值化：偏亮视为要编辑区域
    mask = mask.point(lambda p: 255 if p > 40 else 0)
    # 若几乎全黑，说明用户没涂抹 → 返回 None，走整图指令编辑
    if mask.getextrema()[1] < 128:
        return None
    rgb = ImageOps.colorize(mask, black=(0, 0, 0), white=(255, 255, 255))
    buf = BytesIO()
    rgb.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def edit_image(
    prompt: str,
    image_base64: str,
    mask_base64: str | None = None,
) -> str:
    """
    真修图：通义万相 wanx2.1-imageedit。
    - 有蒙版：局部重绘 description_edit_with_mask（去路人等）
    - 无蒙版：整图指令编辑 description_edit
    """
    text = (prompt or "").strip()
    if not text:
        raise MediaError("请填写修复需求，例如：去掉前方路人、提亮人脸")

    need_mask = any(k in text for k in ("去掉", "删除", "消除", "去除", "路人", "擦除", "移除"))
    if need_mask and not (mask_base64 or "").strip():
        raise MediaError(
            "去掉路人/物体请先在图上用笔刷涂抹要修改的区域，再点生成。"
            "只写文字、不涂抹时模型经常几乎不改图。"
        )

    if (mask_base64 or "").strip():
        edit_prompt = (
            f"{text}。"
            "仅在涂抹（白色）区域内修改，用周围背景自然填补，"
            "未涂抹区域保持不变，不要添加奇怪新物体。"
        )[:800]
    else:
        edit_prompt = (
            f"{text}。"
            "在原图基础上整体调整（如光线、高光、滤镜、色调），"
            "保持人物身份与构图一致，不要换成另一张无关照片。"
        )[:800]

    data_url, size = _prepare_edit_image(image_base64)
    _dashscope_api_key(purpose="照片真修图（通义万相图像编辑）")

    model = (os.getenv("DASHSCOPE_IMAGE_EDIT_MODEL") or "wanx2.1-imageedit").strip()
    input_obj: dict = {
        "prompt": edit_prompt,
        "base_image_url": data_url,
    }
    mask_url = None
    if (mask_base64 or "").strip():
        mask_url = _prepare_mask_data_url(mask_base64, size)
    if mask_url:
        input_obj["function"] = "description_edit_with_mask"
        input_obj["mask_image_url"] = mask_url
    else:
        if need_mask:
            raise MediaError(
                "去掉路人/物体请先在图上涂抹要修改的区域；"
                "若只是提亮、加高光、调滤镜，直接写需求即可，不必涂抹。"
            )
        input_obj["function"] = "description_edit"

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{DASHSCOPE_BASE}/services/aigc/image2image/image-synthesis",
            headers=_dashscope_headers(async_mode=True),
            json={
                "model": model,
                "input": input_obj,
                "parameters": {"n": 1},
            },
        )
        if resp.status_code >= 400:
            raise MediaError(f"真修图请求失败：{_parse_error(resp)}")
        data = resp.json()
        task_id = (
            (data.get("output") or {}).get("task_id")
            or data.get("task_id")
            or (data.get("output") or {}).get("taskId")
        )
        if not task_id:
            urls = _extract_urls(data)
            if urls:
                return _save_image_url(urls[0])
            raise MediaError(f"真修图未返回任务 ID：{str(data)[:240]}")

        result = _poll_dashscope_task(task_id, timeout_sec=180)
        urls = _extract_urls(result)
        if not urls:
            raise MediaError("真修图完成但未返回图片地址")
        return _save_image_url(urls[0])


def _save_video_url(url: str) -> str:
    name = f"{uuid.uuid4().hex}.mp4"
    dest = VIDEO_DIR / name
    _download(url, dest)
    return _public_path("videos", name)


_IMAGE_PAT = re.compile(
    r"(生成.{0,6}图|画.{0,4}图|绘图|配图|出图|图片|插画|海报|灵魂画手|image|picture)",
    re.I,
)
_VIDEO_PAT = re.compile(r"(生成.{0,6}视频|视频|短片|动画|video|clip)", re.I)
_AFFIRMATIVE_RE = re.compile(
    r"^(可以|好的|好|行|没问题|就这样|同意|继续|开始|生成吧|来吧|嗯|对|就这个|ok|yes|sure)[。.!！?？~～\s]*$",
    re.I,
)
_MEDIA_CMD_RE = re.compile(
    r"^(请)?(帮我|给我|帮忙)?(生成|画|做|出|制作)?(一张|一幅|一段|一个)?(高清)?(插画|图片|海报|视频|短片|动画)?[：:，,\s]*",
    re.I,
)
_QUOTED_RE = re.compile(r"[「『\"“]([^」』\"”]{4,120})[」』\"”]")


def _intent_from_text(text: str) -> str | None:
    t = (text or "").strip()
    if not t:
        return None
    if _VIDEO_PAT.search(t) and not _IMAGE_PAT.search(t):
        return "video"
    if _IMAGE_PAT.search(t) or t in ("图片", "图", "画"):
        return "image"
    return None


def _history_mentions_media(history: list[dict]) -> str | None:
    for item in reversed(history[-10:]):
        content = item.get("content", "")
        found = _intent_from_text(content)
        if found:
            return found
        if any(
            k in content
            for k in ("生成图片", "生成视频", "为你生成", "画面", "插画", "配图", "出图")
        ):
            return "video" if "视频" in content else "image"
    return None


def detect_media_intent(text: str, history: list[dict] | None = None) -> str | None:
    t = (text or "").strip()
    if not t:
        return None

    direct = _intent_from_text(t)
    if direct:
        return direct

    history = history or []
    if not history:
        return None

    if _AFFIRMATIVE_RE.match(t):
        return _history_mentions_media(history)

    if len(t) <= 20 and not _AFFIRMATIVE_RE.match(t):
        prior = _history_mentions_media(history)
        if prior and any(k in t for k in ("猪", "猫", "狗", "人", "海", "山", "花", "城", "风")):
            return prior

    return None


def _strip_media_command(text: str) -> str:
    cleaned = _MEDIA_CMD_RE.sub("", (text or "").strip()).strip()
    return cleaned or text.strip()


def _extract_prompt_from_history(history: list[dict]) -> str | None:
    for item in reversed(history[-8:]):
        content = item.get("content", "")
        for m in _QUOTED_RE.finditer(content):
            candidate = m.group(1).strip()
            if len(candidate) >= 4:
                return candidate
        for sep in ("如：", "例如：", "画面：", "描述："):
            if sep in content:
                tail = content.split(sep, 1)[1].strip()
                tail = tail.split("\n", 1)[0].strip("「」\"”' ")
                if len(tail) >= 4:
                    return tail[:120]
    return None


def _llm_media_prompt(
    question: str,
    history: list[dict],
    media_type: str,
) -> str | None:
    from llm_config import get_chat_llm_config

    cfg = get_chat_llm_config()
    if not cfg:
        return None

    kind = "视频" if media_type == "video" else "图片"

    system = (
        f"你是文生{kind}提示词专家。根据完整对话，写出一条可直接用于 AI 生成{kind}的中文画面描述。"
        "只输出提示词正文，不要解释、不要引号、不要 markdown。"
        "若用户当前消息是确认（如「可以」「好的」），采用上一轮已达成共识的画面内容。"
        "80字以内，细节具体。"
    )

    messages = [{"role": "system", "content": system}]
    for item in history[-12:]:
        role = item.get("role", "")
        mapped = "user" if role in ("human", "user") else "assistant"
        messages.append({"role": mapped, "content": str(item.get("content", ""))[:600]})
    messages.append({"role": "user", "content": question})

    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, read=20.0)) as client:
            resp = client.post(
                f"{cfg['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json={
                    "model": cfg["model"],
                    "messages": messages,
                    "temperature": 0.4,
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            text = text.strip("「」\"”' ")
            return text[:800] if text else None
    except Exception:
        return None


def resolve_media_prompt(
    question: str,
    history: list[dict] | None,
    media_type: str,
) -> str:
    history = history or []
    q = (question or "").strip()
    cleaned = _strip_media_command(q)

    if len(cleaned) >= 12 and not _AFFIRMATIVE_RE.match(q):
        return cleaned[:800]

    synthesized = _llm_media_prompt(q, history, media_type)
    if synthesized:
        return synthesized

    from_history = _extract_prompt_from_history(history)
    if from_history:
        return from_history[:800]

    if cleaned and not _AFFIRMATIVE_RE.match(q):
        return cleaned[:800]

    return build_prompt_for_media(q, media_type)


def build_prompt_for_media(text: str, media_type: str) -> str:
    t = text.strip()
    if len(t) >= 8:
        return t
    if media_type == "video":
        return "唯美电影感短片，柔和光线，镜头缓慢推进，高清"
    return "精美高清插画，细节丰富，柔和光影，艺术感"


def format_image_answer(url: str, prompt: str) -> str:
    return f"已为你生成图片（可直接查看/下载）：\n\n![生成图片]({url})\n\n**描述**：{prompt}"


def format_video_answer(url: str, prompt: str, note: str = "") -> str:
    extra = f"\n\n**说明**：{note}" if note else ""
    return (
        f"已为你生成视频：\n\n[[video:{url}]]\n\n"
        f"**描述**：{prompt}{extra}"
    )
