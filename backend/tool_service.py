from sqlalchemy.orm import Session

from chat_service import generate_reply
from database import Tool, User
from media_service import (
    MediaError,
    edit_image,
    format_image_answer,
    format_video_answer,
    generate_image,
    generate_video,
    resolve_media_prompt,
    save_upload_image,
)
from map_service import format_map_answer, geocode_place
from route_service import build_day_route, is_route_question
from ppt_service import format_pptx_answer, generate_pptx_file
from quota_service import QuotaExceededError, require_and_consume
from vip_service import (
    VIP_FEATURE_PPT,
    VIP_FEATURE_VIDEO,
    VipRequiredError,
    require_vip,
)

DRAWING_TOOLS = {"AI灵魂画手", "幻彩画匠"}
PPT_TOOLS = {"PPT狂飙"}
MAP_TOOLS = {"地图工具"}
ROUTE_TOOLS = {"文旅路线规划"}
PHOTO_KEYWORDS = ("照片", "拍照", "修图", "修复", "药品")


def _needs_photo(tool: Tool) -> bool:
    name = tool.name or ""
    desc = tool.description or ""
    return any(k in name or k in desc for k in PHOTO_KEYWORDS)


def run_tool(
    db: Session,
    tool_id: int,
    user_id: int,
    user_input: str,
    image_base64: str | None = None,
    mask_base64: str | None = None,
) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("用户不存在")

    tool = db.get(Tool, tool_id)
    if tool is None:
        raise ValueError("工具不存在")

    text = (user_input or "").strip()
    if not text:
        raise ValueError("请输入内容后再生成")

    upload_url = None
    if _needs_photo(tool):
        if not (image_base64 or "").strip():
            raise ValueError("请先上传照片，再描述要如何修复/处理")
        upload_url = save_upload_image(image_base64)
        require_and_consume(db, user, "image")
        try:
            # 真修图：有涂抹蒙版则局部重绘（去路人），否则整图指令编辑
            out_url = edit_image(text, image_base64, mask_base64)
        except MediaError:
            raise
        mode = "局部重绘（已涂抹区域）" if (mask_base64 or "").strip() else "整图指令编辑"
        output = (
            f"已基于你上传的**原图**完成修图（通义万相 · {mode}）。\n\n"
            f"修复需求：{text}\n\n"
            f"原图：{upload_url}\n\n"
            f"{format_image_answer(out_url, text)}"
        )
        return {
            "tool_id": tool.id,
            "tool_name": tool.name,
            "input": text,
            "output": output,
            "media_url": out_url,
            "upload_url": upload_url,
            "media_type": "image",
        }

    if tool.name in DRAWING_TOOLS or "画" in tool.name:
        prompt = resolve_media_prompt(text, [], "image")
        require_and_consume(db, user, "image")
        try:
            url = generate_image(prompt)
            result = format_image_answer(url, prompt)
            return {
                "tool_id": tool.id,
                "tool_name": tool.name,
                "input": text,
                "output": result,
                "media_url": url,
                "media_type": "image",
            }
        except MediaError:
            raise

    if tool.name in PPT_TOOLS or "PPT" in tool.name.upper():
        require_vip(user, VIP_FEATURE_PPT)
        meta = generate_pptx_file(text)
        return {
            "tool_id": tool.id,
            "tool_name": tool.name,
            "input": text,
            "output": format_pptx_answer(meta),
            "file_url": meta["file_url"],
            "filename": meta["filename"],
            "media_type": "pptx",
        }

    if tool.name in MAP_TOOLS or "地图" in (tool.name or ""):
        require_and_consume(db, user, "chat")
        point = geocode_place(text)
        return {
            "tool_id": tool.id,
            "tool_name": tool.name,
            "input": text,
            "output": format_map_answer(point),
            "map": point,
            "media_type": "map",
        }

    if tool.name in ROUTE_TOOLS or "路线" in (tool.name or ""):
        require_and_consume(db, user, "chat")
        q = text if is_route_question(text) else f"{text}一日游路线规划"
        try:
            data = build_day_route(q)
        except ValueError as e:
            raise ValueError(str(e)) from e
        return {
            "tool_id": tool.id,
            "tool_name": tool.name,
            "input": text,
            "output": data["answer"],
            "stops": data["stops"],
            "media_type": "route",
        }

    require_and_consume(db, user, "chat")
    system = tool.system_prompt or (
        f"你是「{tool.name}」助手。{tool.description} 用结构化中文输出，简洁实用。"
    )
    result = generate_reply(text, system, tool_name=tool.name)
    return {
        "tool_id": tool.id,
        "tool_name": tool.name,
        "input": text,
        "output": result,
    }


def run_media(db: Session, user_id: int, media_type: str, prompt: str) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("用户不存在")
    p = resolve_media_prompt(prompt, [], media_type)
    if media_type == "video":
        require_vip(user, VIP_FEATURE_VIDEO)
        url, note = generate_video(p)
        return {
            "media_type": "video",
            "media_url": url,
            "output": format_video_answer(url, p, note),
        }
    require_and_consume(db, user, "image")
    url = generate_image(p)
    return {
        "media_type": "image",
        "media_url": url,
        "output": format_image_answer(url, p),
    }
