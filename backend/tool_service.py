from sqlalchemy.orm import Session

from chat_service import generate_reply
from database import Tool, User
from media_service import (
    MediaError,
    format_image_answer,
    format_video_answer,
    generate_image,
    generate_video,
    resolve_media_prompt,
)
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


def run_tool(db: Session, tool_id: int, user_id: int, user_input: str) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("用户不存在")

    tool = db.get(Tool, tool_id)
    if tool is None:
        raise ValueError("工具不存在")

    text = (user_input or "").strip()
    if not text:
        raise ValueError("请输入内容后再生成")

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
        url = generate_video(p)
        return {
            "media_type": "video",
            "media_url": url,
            "output": format_video_answer(url, p),
        }
    require_and_consume(db, user, "image")
    url = generate_image(p)
    return {
        "media_type": "image",
        "media_url": url,
        "output": format_image_answer(url, p),
    }
