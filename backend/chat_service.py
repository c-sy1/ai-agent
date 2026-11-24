import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
from sqlalchemy.orm import Session

from database import Agent, ChatMessage, Conversation, ROLE_AI, ROLE_HUMAN, User
from llm_config import get_chat_llm_config
from media_service import (
    MediaError,
    detect_media_intent,
    format_image_answer,
    format_video_answer,
    generate_image,
    generate_video,
    parse_video_duration,
    resolve_media_prompt,
    video_prompt_lacks_scene,
)
from quota_service import QuotaExceededError, require_and_consume
from map_service import format_map_answer, try_resolve_map
from search_service import fetch_search, is_search_question
from vip_service import VIP_FEATURE_VIDEO, VipRequiredError, require_vip
from weather_service import fetch_weather, is_weather_question

PM_INTERVIEW_REPLY = """产品经理面试通常涵盖以下六大模块，建议逐条准备：

1. **行为面试（Behavioral）**
   - 考察过往项目经历、跨团队协作、冲突处理。
   - 常用 STAR 法则：情境、任务、行动、结果。
   - 示例：「讲一次你推动需求从 0 到 1 上线的经历。」

2. **案例分析（Case Study）**
   - 给定业务场景做需求拆解、优先级排序或指标设计。
   - 示例：「某 App 次日留存下降，你会如何排查并制定方案？」

3. **产品 Sense / 产品设计**
   - 考察用户洞察、功能设计、体验细节。
   - 示例：「为老年人设计一款打车产品，你会关注哪些点？」

4. **数据与指标**
   - 熟悉北极星指标、漏斗、A/B 测试基本思路。
   - 示例：「如何衡量一个社区功能是否成功？」

5. **技术理解（Tech）**
   - 不要求写代码，但要理解 API、埋点、发布流程、技术成本。
   - 示例：「前后端分离架构下，产品如何参与接口评审？」

6. **战略与商业**
   - 竞品分析、商业模式、增长策略。
   - 示例：「短视频与直播电商的异同，你会如何布局？」

**备考建议**：每个模块准备 2～3 个真实项目故事；针对目标公司做竞品与用户画像功课；模拟面试录音复盘表达逻辑。"""


def _demo_reply(question: str, agent: Optional[Agent]) -> str:
    q = question.strip()
    if "产品经理面试" in q or "PM面试" in q:
        return PM_INTERVIEW_REPLY
    if agent:
        return (
            f"你好，我是「{agent.name}」。{agent.description}\n\n"
            f"你刚才说：「{q}」\n\n"
            "（当前为演示模式：请在 backend/.env 中配置 ZHIPU_API_KEY 以启用智谱大模型回复。）"
        )
    if "天气" in q:
        return "今天以多云为主，气温 18～26℃，早晚略凉，建议带一件薄外套。"
    if "穿什么" in q or "穿搭" in q:
        return "建议商务休闲：浅色衬衫 + 深色休闲裤 + 轻便外套，舒适又得体。"
    return (
        f"已收到你的问题：「{q}」\n\n"
        "我是 Apex AI 助手。你可以尝试：快速写作、语言翻译、拍照答疑，或在「工具箱」「智能体广场」选择具体能力。"
        "\n\n（演示模式：配置 ZHIPU_API_KEY 后可获得完整 AI 对话。）"
    )


def _llm_reply(
    question: str,
    history: list[dict],
    system_prompt: str,
) -> Optional[str]:
    cfg = get_chat_llm_config()
    if not cfg:
        return None

    # 明确要求使用会话历史，避免模型套用「我没有记忆」话术
    sys = (system_prompt or "").strip() or "你是 Apex AI 助手。"
    sys += (
        "\n\n【会话规则】本请求 messages 中更早的 user/assistant 即当前会话历史。"
        "必须结合这些历史连贯回答；用户问「还记得吗/我刚问了什么」时直接复述上文。"
        "禁止说没有记忆、每次对话独立、无法回忆本会话内容。"
    )
    messages = [{"role": "system", "content": sys}]
    for item in history[-20:]:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        raw_role = (item.get("role") or "").strip().lower()
        role = "user" if raw_role in ("human", "user") else "assistant"
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    timeout = httpx.Timeout(20.0, read=float(os.getenv("QIANWEN_READ_TIMEOUT", "120")))
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{cfg['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json={
                    "model": cfg["model"],
                    "messages": messages,
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"].get("content")
            if isinstance(content, str) and content.strip():
                return content
            return None
    except httpx.TimeoutException:
        return "__TIMEOUT__"
    except Exception as e:
        print(f"[llm_reply] failed ({cfg.get('provider')}): {type(e).__name__}: {e}")
        return None


def _timeout_message(question: str, label: str = "Apex AI") -> str:
    return (
        f"【{label}】\n\n"
        f"已收到：{question.strip()}\n\n"
        "大模型响应超时。请稍后再试一次；"
        "也可在 backend/.env 增大 QIANWEN_READ_TIMEOUT。"
    )


def _unwrap_llm(raw: Optional[str], question: str, label: str = "Apex AI") -> Optional[str]:
    if raw == "__TIMEOUT__":
        return _timeout_message(question, label)
    return raw


def generate_reply(
    question: str,
    system_prompt: str,
    history: Optional[list[dict]] = None,
    tool_name: str = "",
) -> str:
    history = history or []
    label = tool_name or "Apex AI"
    answer = _unwrap_llm(_llm_reply(question, history, system_prompt), question, label)
    if answer is not None:
        return answer
    return (
        f"【{label} · 演示回复】\n\n"
        f"已收到：{question.strip()}\n\n"
        "当前未连上大模型或请求失败。请检查 backend/.env 中的 ZHIPU_API_KEY，"
        "或稍后重试。配置成功后，此处会返回完整的 AI 生成结果。"
    )


def chat_in_conversation(
    db: Session,
    user_id: int,
    conversation_id: int,
    question: str,
) -> str:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if conv is None:
        raise ValueError("会话不存在")

    agent = db.get(Agent, conv.agent_id) if conv.agent_id else None
    system_prompt = (
        agent.system_prompt
        if agent and agent.system_prompt
        else (
            "你是 Apex AI 全能助手，用简洁清晰的中文回答。"
            "你会记住并使用当前会话中的历史消息来连贯对话。"
        )
    )

    history_rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id)
        .all()
    )
    history = [{"role": r.role, "content": r.content} for r in history_rows]

    db.add(
        ChatMessage(
            conversation_id=conversation_id,
            user_id=user_id,
            role=ROLE_HUMAN,
            content=question,
        )
    )
    db.commit()

    media_type = detect_media_intent(question, history)
    user = db.get(User, user_id)

    answer = None
    # 实时能力：天气优先，避免「保定天气」被地图抢答
    if answer is None and is_weather_question(question):
        try:
            require_and_consume(db, user, "chat")
            answer = fetch_weather(question)
        except QuotaExceededError as e:
            answer = (
                f"🔒 {e}\n\n"
                "开通入口：左下角进入「个人主页」选择套餐充值。"
            )
    # 地图工具：内置地点坐标（保定 / 白洋淀 / 狼牙山）
    if answer is None:
        point = try_resolve_map(question)
        if point is not None:
            try:
                require_and_consume(db, user, "chat")
                answer = format_map_answer(point)
            except QuotaExceededError as e:
                answer = (
                    f"🔒 {e}\n\n"
                    "开通入口：左下角进入「个人主页」选择套餐充值。"
                )
    if answer is None and is_search_question(question):
        try:
            require_and_consume(db, user, "chat")
            answer = fetch_search(question) or (
                "联网检索暂时没有可用结果，请换个问法再试。"
            )
        except QuotaExceededError as e:
            answer = (
                f"🔒 {e}\n\n"
                "开通入口：左下角进入「个人主页」选择套餐充值。"
            )

    if answer is None and media_type:
        # 只说「生成十秒视频」、没写画面 → 先追问，避免模型乱编场景
        if media_type == "video" and video_prompt_lacks_scene(question):
            want = parse_video_duration(question)
            dur_tip = (
                f"你提到约 {want} 秒；"
                if want
                else ""
            )
            answer = (
                "可以生成视频，但还缺画面内容。\n\n"
                "请补充具体场景，例如：\n"
                "「夕阳海边，一只金毛犬在沙滩上奔跑」\n"
                "「赛博朋克夜市，霓虹灯下人群穿梭」\n\n"
                f"{dur_tip}"
                "说明：免费/常用模型单条约 3～5 秒；"
                "要 10 秒需开启付费万相（费用更高）。"
            )
        else:
            prompt = resolve_media_prompt(question, history, media_type)
            try:
                if media_type == "video":
                    require_vip(user, VIP_FEATURE_VIDEO)
                    want = parse_video_duration(question) or parse_video_duration(
                        prompt
                    )
                    url, note = generate_video(prompt, duration=want)
                    answer = format_video_answer(url, prompt, note)
                else:
                    require_and_consume(db, user, "image")
                    url = generate_image(prompt)
                    answer = format_image_answer(url, prompt)
            except QuotaExceededError as e:
                answer = (
                    f"🔒 {e}\n\n"
                    "开通入口：左下角进入「个人主页」选择套餐充值。"
                )
            except VipRequiredError as e:
                answer = (
                    f"🔒 {e}\n\n"
                    "开通入口：左侧进入「个人主页」选择套餐，用支付宝完成支付；"
                    "管理员也可在「管理后台」直接开通 VIP。"
                )
            except MediaError as e:
                kind = "视频" if media_type == "video" else "图片"
                tip = (
                    "图片已优先走魔搭免费文生图。"
                    if media_type == "image"
                    else (
                        "视频为 VIP 功能；开通后走魔搭免费通道（可能排队）。"
                        "若魔搭 429：等一两分钟再试。"
                    )
                )
                answer = (
                    f"⚠️ 真实{kind}生成失败\n\n"
                    f"{e}\n\n"
                    f"{tip}\n\n"
                    "下面先给你文字版分镜/说明：\n\n"
                )
                text_part = _unwrap_llm(
                    _llm_reply(question, history, system_prompt), question
                )
                answer += text_part or _demo_reply(question, agent)

    if answer is None:
        try:
            require_and_consume(db, user, "chat")
        except QuotaExceededError as e:
            answer = (
                f"🔒 {e}\n\n"
                "开通入口：左下角进入「个人主页」选择套餐充值，解锁更高对话额度。"
            )
        else:
            answer = _unwrap_llm(_llm_reply(question, history, system_prompt), question)
            if answer is None:
                answer = _demo_reply(question, agent)

    db.add(
        ChatMessage(
            conversation_id=conversation_id,
            user_id=user_id,
            role=ROLE_AI,
            content=answer,
        )
    )
    if conv.title == "新对话" and question.strip():
        conv.title = question.strip()[:50]
    db.commit()
    return answer
