from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth_service import (
    assert_self_or_admin,
    auth_payload_for,
    check_login_rate_limit,
    clear_login_failures,
    get_current_user,
    hash_password,
    is_hashed_password,
    record_login_failure,
    require_admin,
    verify_password,
)
from chat_service import chat_in_conversation
from tool_service import run_tool, run_media

from media_service import GENERATED_ROOT, MediaError
from database import (
    Agent,
    ChatMessage,
    Conversation,
    HotTopic,
    RechargeOrder,
    Tool,
    User,
    get_db,
    init_db,
)
from seed import seed
from payment_service import (
    PaymentConfigError,
    alipay_configured,
    build_page_pay_url,
    verify_alipay_callback,
)
from quota_service import QuotaExceededError, usage_summary
from vip_service import (
    VIP_FEATURE_LABELS,
    VIP_PACKAGES,
    VipRequiredError,
    create_vip_order,
    extend_vip,
    mark_order_paid,
    revoke_vip,
    vip_status,
)

app = FastAPI(title="Apex AI API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
seed()

GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=str(GENERATED_ROOT)), name="generated")


class RegisterReq(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str
    password: str = Field(min_length=6, max_length=72)
    nickname: str = ""


class LoginReq(BaseModel):
    username: str
    password: str


class ChatReq(BaseModel):
    user_id: int
    conversation_id: int | None = None
    question: str
    agent_id: int | None = None


class ConversationCreateReq(BaseModel):
    user_id: int
    title: str = "新对话"
    agent_id: int | None = None


class ToolInvokeReq(BaseModel):
    user_id: int
    input: str
    image_base64: str | None = None
    mask_base64: str | None = None


class ConversationUpdateReq(BaseModel):
    user_id: int
    title: str | None = None
    is_pinned: int | None = None


class ConversationDeleteReq(BaseModel):
    user_id: int


class MediaGenerateReq(BaseModel):
    user_id: int
    prompt: str
    media_type: str = "image"  # image | video


def _apply_conversation_update(conv: Conversation, req: ConversationUpdateReq):
    if req.title is not None:
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        conv.title = title[:200]
    if req.is_pinned is not None:
        conv.is_pinned = 1 if req.is_pinned else 0


def _user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def _conv_or_404(db: Session, conversation_id: int, user_id: int) -> Conversation:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


def _conv_item(r: Conversation) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "is_pinned": bool(r.is_pinned),
        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
    }


@app.post("/api/register")
def register(req: RegisterReq, db: Session = Depends(get_db)):
    username = req.username.strip()
    email = req.email.strip().lower()
    if not username or not email:
        raise HTTPException(status_code=400, detail="用户名和邮箱不能为空")
    exists = (
        db.query(User)
        .filter(or_(User.username == username, User.email == email))
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="用户名或邮箱已被注册")

    user = User(
        username=username,
        email=email,
        password=hash_password(req.password),
        nickname=(req.nickname or username).strip()[:50],
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="用户名或邮箱已被注册")
    db.refresh(user)
    return {
        "code": 200,
        "msg": "注册成功",
        "data": auth_payload_for(user),
    }


@app.post("/api/login")
def login(req: LoginReq, request: Request, db: Session = Depends(get_db)):
    username = (req.username or "").strip()
    ip = request.client.host if request.client else None
    check_login_rate_limit(username, ip)

    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(req.password, user.password or ""):
        record_login_failure(username, ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 旧明文密码登录成功后自动升级为 bcrypt
    if not is_hashed_password(user.password or ""):
        user.password = hash_password(req.password)
        db.commit()
        db.refresh(user)

    clear_login_failures(username, ip)
    return {
        "code": 200,
        "msg": "登录成功",
        "data": auth_payload_for(user),
    }


@app.get("/api/auth/me")
def auth_me(auth: User = Depends(get_current_user)):
    return {"code": 200, "data": auth_payload_for(auth)}


class ProfileUpdateReq(BaseModel):
    user_id: int
    nickname: str | None = None
    email: str | None = None


@app.get("/api/users/{user_id}/profile")
def get_profile(
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    user = _user_or_404(db, user_id)
    conv_count = (
        db.query(Conversation).filter(Conversation.user_id == user_id).count()
    )
    msg_count = (
        db.query(ChatMessage).filter(ChatMessage.user_id == user_id).count()
    )
    return {
        "code": 200,
        "data": {
            "user_id": user.id,
            "username": user.username,
            "nickname": user.nickname or user.username,
            "email": user.email,
            "avatar": user.avatar or "",
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "conversation_count": conv_count,
            "message_count": msg_count,
            **vip_status(user),
            "usage": usage_summary(db, user),
        },
    }


@app.get("/api/users/{user_id}/usage")
def get_usage(
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    user = _user_or_404(db, user_id)
    return {"code": 200, "data": usage_summary(db, user)}


@app.post("/api/users/profile/update")
def update_profile(
    req: ProfileUpdateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    user = _user_or_404(db, req.user_id)
    if req.nickname is not None:
        nick = req.nickname.strip()
        if not nick:
            raise HTTPException(status_code=400, detail="昵称不能为空")
        user.nickname = nick[:50]
    if req.email is not None:
        email = req.email.strip()
        if not email or "@" not in email:
            raise HTTPException(status_code=400, detail="邮箱格式不正确")
        exists = (
            db.query(User)
            .filter(User.email == email, User.id != user.id)
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="该邮箱已被占用")
        user.email = email[:100]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="资料更新失败")
    db.refresh(user)
    return {
        "code": 200,
        "msg": "资料已更新",
        "data": {
            "user_id": user.id,
            "username": user.username,
            "nickname": user.nickname or user.username,
            "email": user.email,
        },
    }


@app.get("/api/health")
def health():
    return {"code": 200, "ok": True}


@app.get("/api/hot-topics")
def hot_topics(db: Session = Depends(get_db)):
    rows = db.query(HotTopic).order_by(HotTopic.rank).all()
    return {
        "code": 200,
        "data": [{"rank": r.rank, "title": r.title, "heat": r.heat} for r in rows],
    }


@app.get("/api/tools")
def list_tools(
    category: str | None = Query(None),
    q: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Tool)
    if category and category != "all":
        query = query.filter(Tool.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Tool.name.like(like), Tool.description.like(like)))
    rows = query.order_by(Tool.sort_order).all()
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "category": r.category,
                "tag": r.tag,
                "icon": r.icon,
                "input_placeholder": r.input_placeholder,
                "vip_required": r.name == "PPT狂飙" or "PPT" in (r.name or "").upper(),
            }
            for r in rows
        ],
    }


@app.get("/api/tools/{tool_id}")
def get_tool(tool_id: int, db: Session = Depends(get_db)):
    tool = db.get(Tool, tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="工具不存在")
    return {
        "code": 200,
        "data": {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "tag": tool.tag,
            "icon": tool.icon,
            "input_placeholder": tool.input_placeholder,
        },
    }


@app.post("/api/tools/{tool_id}/invoke")
def invoke_tool(
    tool_id: int,
    req: ToolInvokeReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    try:
        data = run_tool(
            db, tool_id, req.user_id, req.input, req.image_base64, req.mask_base64
        )
    except QuotaExceededError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except VipRequiredError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except MediaError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 200, "msg": "生成成功", "data": data}


@app.post("/api/media/generate")
def media_generate(
    req: MediaGenerateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    _user_or_404(db, req.user_id)
    if req.media_type not in ("image", "video"):
        raise HTTPException(status_code=400, detail="media_type 只能是 image 或 video")
    try:
        data = run_media(db, req.user_id, req.media_type, req.prompt)
    except QuotaExceededError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except VipRequiredError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except MediaError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 200, "msg": "生成成功", "data": data}


@app.get("/api/agents")
def list_agents(
    category: str | None = Query(None),
    q: str | None = Query(None),
    featured: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Agent)
    if featured is not None:
        query = query.filter(Agent.featured == featured)
    if category and category not in ("全部分类", "all"):
        query = query.filter(Agent.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Agent.name.like(like), Agent.description.like(like)))
    rows = query.order_by(Agent.sort_order).all()
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "category": r.category,
                "author": r.author,
                "likes": r.likes,
                "heat": r.heat,
                "icon": r.icon,
            }
            for r in rows
        ],
    }


@app.get("/api/conversations")
def list_conversations(
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    _user_or_404(db, user_id)
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
        .all()
    )
    now = datetime.utcnow()
    month_ago = now - timedelta(days=30)
    half_year = now - timedelta(days=180)

    pinned = []
    recent_month = []
    recent_half = []
    for r in rows:
        item = _conv_item(r)
        if r.is_pinned:
            pinned.append(item)
            continue
        ts = r.updated_at or r.created_at
        if ts and ts >= month_ago:
            recent_month.append(item)
        elif ts and ts >= half_year:
            recent_half.append(item)
        else:
            recent_half.append(item)

    return {
        "code": 200,
        "data": {
            "pinned": pinned,
            "recent_month": recent_month,
            "recent_half_year": recent_half,
        },
    }


@app.patch("/api/conversations/{conversation_id}")
def update_conversation(
    conversation_id: int,
    req: ConversationUpdateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    conv = _conv_or_404(db, conversation_id, req.user_id)
    _apply_conversation_update(conv, req)
    db.commit()
    db.refresh(conv)
    return {"code": 200, "data": _conv_item(conv)}


@app.post("/api/conversations/{conversation_id}/update")
def update_conversation_post(
    conversation_id: int,
    req: ConversationUpdateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    return update_conversation(conversation_id, req, db, auth)


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    conv = _conv_or_404(db, conversation_id, user_id)
    db.delete(conv)
    db.commit()
    return {"code": 200, "msg": "已删除"}


@app.post("/api/conversations/{conversation_id}/remove")
def delete_conversation_post(
    conversation_id: int,
    req: ConversationDeleteReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    return delete_conversation(conversation_id, req.user_id, db, auth)


@app.post("/api/conversations")
def create_conversation(
    req: ConversationCreateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    _user_or_404(db, req.user_id)
    conv = Conversation(
        user_id=req.user_id,
        title=req.title,
        agent_id=req.agent_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"code": 200, "data": {"id": conv.id, "title": conv.title}}


@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    _user_or_404(db, user_id)
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id)
        .all()
    )
    return {
        "code": 200,
        "data": [
            {
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for r in rows
        ],
    }


@app.post("/api/chat")
def chat(
    req: ChatReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    _user_or_404(db, req.user_id)
    conv_id = req.conversation_id
    if conv_id is None:
        conv = Conversation(
            user_id=req.user_id,
            title="新对话",
            agent_id=req.agent_id,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conv_id = conv.id

    try:
        answer = chat_in_conversation(db, req.user_id, conv_id, req.question)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return {
        "code": 200,
        "msg": "调用成功",
        "data": {"answer": answer, "conversation_id": conv_id},
    }


@app.get("/api/session/{user_id}/history")
def legacy_history(
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    """兼容课程模版的历史接口：返回该用户最近一条会话的全部消息。"""
    assert_self_or_admin(auth, user_id)
    _user_or_404(db, user_id)
    conv = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if conv is None:
        return {"code": 200, "msg": "调用成功", "data": []}
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.id)
        .all()
    )
    return {
        "code": 200,
        "msg": "调用成功",
        "data": [
            {
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for r in rows
        ],
    }


def _admin_or_403(db: Session, admin_user_id: int) -> User:
    admin = _user_or_404(db, admin_user_id)
    if int(getattr(admin, "is_admin", 0) or 0) != 1:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return admin


class RechargeReq(BaseModel):
    user_id: int
    package_id: str


class OrderActionReq(BaseModel):
    user_id: int


class AdminGrantVipReq(BaseModel):
    admin_user_id: int
    user_id: int
    days: int = 30


class AdminRevokeVipReq(BaseModel):
    admin_user_id: int
    user_id: int


@app.get("/api/vip/packages")
def vip_packages():
    return {
        "code": 200,
        "data": {
            "packages": VIP_PACKAGES,
            "features": VIP_FEATURE_LABELS,
            "pay_ready": alipay_configured(),
            "pay_channel": "alipay",
        },
    }


@app.get("/api/vip/status")
def get_vip_status(
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    user = _user_or_404(db, user_id)
    return {"code": 200, "data": vip_status(user)}


@app.post("/api/vip/recharge")
def vip_recharge(
    req: RechargeReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    """创建 VIP 订单并返回支付宝支付链接（支付成功后才开通）。"""
    assert_self_or_admin(auth, req.user_id)
    user = _user_or_404(db, req.user_id)
    try:
        order, pay_url = create_vip_order(db, user, req.package_id)
    except PaymentConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "code": 200,
        "msg": "订单已创建，请完成支付宝支付",
        "data": {
            "order_id": order.id,
            "out_trade_no": order.out_trade_no,
            "package_name": order.package_name,
            "amount": order.amount,
            "days": order.days,
            "status": order.status,
            "pay_url": pay_url,
            "pay_ready": alipay_configured(),
        },
    }


@app.get("/api/vip/orders/{order_id}")
def vip_order_detail(
    order_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    _user_or_404(db, user_id)
    order = db.get(RechargeOrder, order_id)
    if order is None or order.user_id != user_id:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {
        "code": 200,
        "data": {
            "id": order.id,
            "out_trade_no": order.out_trade_no,
            "package_name": order.package_name,
            "amount": order.amount,
            "days": order.days,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else "",
        },
    }


@app.post("/api/vip/orders/{order_id}/cancel")
def vip_cancel_order(
    order_id: int,
    req: OrderActionReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    _user_or_404(db, req.user_id)
    order = db.get(RechargeOrder, order_id)
    if order is None or order.user_id != req.user_id:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="只能取消待支付订单")
    order.status = "cancelled"
    order.remark = "用户取消"
    db.commit()
    return {"code": 200, "msg": "订单已取消"}


@app.post("/api/vip/orders/{order_id}/pay")
def vip_continue_pay(
    order_id: int,
    req: OrderActionReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    """待支付订单重新生成支付宝跳转链接。"""
    assert_self_or_admin(auth, req.user_id)
    _user_or_404(db, req.user_id)
    order = db.get(RechargeOrder, order_id)
    if order is None or order.user_id != req.user_id:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="订单不是待支付状态")
    if not order.out_trade_no:
        raise HTTPException(status_code=400, detail="订单缺少支付单号")
    try:
        pay_url = build_page_pay_url(
            out_trade_no=order.out_trade_no,
            subject=f"Apex AI {order.package_name}",
            total_amount=order.amount,
        )
    except PaymentConfigError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {
        "code": 200,
        "msg": "请完成支付宝支付",
        "data": {"pay_url": pay_url, "order_id": order.id},
    }


@app.post("/api/pay/alipay/notify")
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if not verify_alipay_callback(params):
        return PlainTextResponse("fail")
    trade_status = params.get("trade_status", "")
    if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        mark_order_paid(
            db,
            params.get("out_trade_no", ""),
            trade_no=params.get("trade_no", ""),
        )
    return PlainTextResponse("success")


@app.get("/api/pay/alipay/return")
def alipay_return(
    db: Session = Depends(get_db),
    out_trade_no: str = "",
    trade_no: str = "",
    trade_status: str = "",
):
    """同步跳转：校验后开通并回到个人页。"""
    # return 场景参数也带签名，但浏览器 GET 可能不完整；以 out_trade_no 查询本地订单并依赖 notify 为准。
    # 沙箱/联调时若已带成功状态，则尝试开通。
    if out_trade_no and trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED", ""):
        # 有 out_trade_no 时尝试开通（notify 会再幂等一次）
        if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED") or trade_no:
            mark_order_paid(db, out_trade_no, trade_no=trade_no)
    return RedirectResponse(url="/profile?pay=1", status_code=302)


@app.get("/api/vip/orders")
def vip_orders(
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, user_id)
    _user_or_404(db, user_id)
    rows = (
        db.query(RechargeOrder)
        .filter(RechargeOrder.user_id == user_id)
        .order_by(RechargeOrder.id.desc())
        .limit(50)
        .all()
    )
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "out_trade_no": r.out_trade_no,
                "package_name": r.package_name,
                "amount": r.amount,
                "days": r.days,
                "status": r.status,
                "channel": r.channel,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.get("/api/admin/users")
def admin_list_users(
    admin_user_id: int = 0,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    rows = db.query(User).order_by(User.id.desc()).limit(200).all()
    return {
        "code": 200,
        "data": [
            {
                "user_id": u.id,
                "username": u.username,
                "nickname": u.nickname or u.username,
                "email": u.email,
                **vip_status(u),
            }
            for u in rows
        ],
    }


@app.post("/api/admin/vip/grant")
def admin_grant_vip(
    req: AdminGrantVipReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    user = _user_or_404(db, req.user_id)
    extend_vip(user, req.days)
    db.commit()
    db.refresh(user)
    return {"code": 200, "msg": f"已开通 {req.days} 天 VIP", "data": vip_status(user)}


@app.post("/api/admin/vip/revoke")
def admin_revoke_vip(
    req: AdminRevokeVipReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    user = _user_or_404(db, req.user_id)
    revoke_vip(user)
    db.commit()
    db.refresh(user)
    return {"code": 200, "msg": "已取消 VIP", "data": vip_status(user)}


@app.get("/api/admin/recharges")
def admin_recharges(
    admin_user_id: int = 0,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    rows = db.query(RechargeOrder).order_by(RechargeOrder.id.desc()).limit(100).all()
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "out_trade_no": r.out_trade_no,
                "user_id": r.user_id,
                "package_name": r.package_name,
                "amount": r.amount,
                "days": r.days,
                "status": r.status,
                "channel": r.channel,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


# 前端构建产物：同一端口同时提供 API + 页面
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
@app.get("/api/works")
def list_works(
    kind: str = Query("all"),
    limit: int = Query(60, ge=1, le=200),
    auth: User = Depends(get_current_user),
):
    """列出本机已生成的图片/视频（作品中心）。"""
    from media_service import IMAGE_DIR, UPLOAD_DIR, VIDEO_DIR

    _ = auth  # 需登录可见
    items: list[dict] = []

    def collect(folder: Path, media_kind: str, url_prefix: str):
        if not folder.is_dir():
            return
        for path in folder.iterdir():
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if media_kind == "image" and suffix not in (
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".gif",
            ):
                continue
            if media_kind == "video" and suffix not in (".mp4", ".webm", ".mov"):
                continue
            try:
                mtime = path.stat().st_mtime
                size = path.stat().st_size
            except OSError:
                continue
            items.append(
                {
                    "id": f"{media_kind}-{path.name}",
                    "name": path.name,
                    "kind": media_kind,
                    "url": f"/generated/{url_prefix}/{path.name}",
                    "size": size,
                    "mtime": mtime,
                }
            )

    k = (kind or "all").lower()
    if k in ("all", "image"):
        collect(IMAGE_DIR, "image", "images")
        collect(UPLOAD_DIR, "image", "uploads")
    if k in ("all", "video"):
        collect(VIDEO_DIR, "video", "videos")

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"code": 200, "data": items[:limit]}


_ASSETS_DIR = _FRONTEND_DIST / "assets"
if _ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


@app.get("/")
def spa_index():
    index = _FRONTEND_DIST / "index.html"
    if not index.is_file():
        return {"msg": "前端未构建，请先在 frontend 目录执行 npm run build"}
    return FileResponse(index)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """非 /api 路径回退到 React 路由（如 /login）。"""
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
        raise HTTPException(status_code=404, detail="Not Found")
    candidate = _FRONTEND_DIST / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    index = _FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="前端未构建")
