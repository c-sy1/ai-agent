import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
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
    require_admin_mfa,
    verify_password,
)
from chat_service import chat_in_conversation
from tool_service import run_tool, run_media
from map_service import (
    geocode_place,
    list_places,
    parse_all_map_markers,
    parse_map_marker,
    realtime_enabled,
)

from media_service import GENERATED_ROOT, MediaError
from coupon_service import (
    claim_coupon,
    grant_support_coupon,
    grant_welcome_coupon,
    list_campaign_coupons,
    list_grantable_coupons,
    list_user_coupons,
)
from database import (
    AdminOpLog,
    Agent,
    ChatFeedback,
    ChatMessage,
    Conversation,
    HotTopic,
    KnowledgeDoc,
    RechargeOrder,
    SmsLog,
    SupportTicket,
    Tool,
    User,
    UserCoupon,
    SessionLocal,
    get_db,
    init_db,
)
from knowledge_service import KB_CATEGORIES, ensure_seed_docs, list_docs
from email_service import (
    EMAIL_SCENES,
    email_configured,
    mask_email,
    normalize_email,
    send_email_code,
    user_by_email,
    verify_email_code,
)
from sms_service import (
    CODE_SCENES,
    alert_login_attack,
    assert_phone_free,
    grant_admin_mfa,
    mask_phone,
    mfa_active,
    normalize_phone,
    note_remote_login,
    notify_admin_risk,
    notify_user,
    notify_vip_opened,
    send_code,
    user_by_phone,
    verify_code,
)
from seed import seed
from payment_service import (
    PaymentConfigError,
    alipay_configured,
    verify_alipay_callback,
)
from wechat_pay_service import (
    WechatPaymentConfigError,
    decrypt_notify_resource,
    wechat_configured,
)
from quota_service import QuotaExceededError, usage_summary
from vip_service import (
    VIP_FEATURE_LABELS,
    VIP_PACKAGES,
    VipRequiredError,
    create_vip_order,
    extend_vip,
    get_package,
    list_public_packages,
    mark_order_paid,
    rebuild_pay_payload,
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
with SessionLocal() as _db:
    ensure_seed_docs(_db)

GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=str(GENERATED_ROOT)), name="generated")


class RegisterReq(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str
    password: str = Field(min_length=6, max_length=72)
    nickname: str = ""
    phone: str = ""
    sms_code: str = ""  # 兼容旧字段；优先用 email_code
    email_code: str = ""


class LoginReq(BaseModel):
    username: str
    password: str


class SmsSendReq(BaseModel):
    phone: str
    scene: str


class EmailSendReq(BaseModel):
    email: str
    scene: str


class PhoneLoginReq(BaseModel):
    phone: str
    sms_code: str


class EmailLoginReq(BaseModel):
    email: str
    email_code: str


class ResetPasswordReq(BaseModel):
    phone: str = ""
    sms_code: str = ""
    email: str = ""
    email_code: str = ""
    new_password: str = Field(min_length=6, max_length=72)


class BindPhoneReq(BaseModel):
    phone: str
    sms_code: str


class AdminMfaReq(BaseModel):
    sms_code: str


class AdminDisableReq(BaseModel):
    user_id: int
    disabled: bool = True


class AdminResetPasswordReq(BaseModel):
    user_id: int
    new_password: str = Field(min_length=6, max_length=72)


class AdminQuotaReq(BaseModel):
    user_ids: list[int]
    chat_extra: int = 0
    image_extra: int = 0


class AdminApproveOrderReq(BaseModel):
    order_id: int


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


class MapGeocodeReq(BaseModel):
    place: str = Field(..., min_length=1, max_length=64)


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
    email = normalize_email(req.email)
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    exists = (
        db.query(User)
        .filter(or_(User.username == username, User.email == email))
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="用户名或邮箱已被注册")

    code = (req.email_code or req.sms_code or "").strip()
    verify_email_code(db, email, "register", code)

    phone = ""
    if (req.phone or "").strip():
        phone = assert_phone_free(db, req.phone)

    user = User(
        username=username,
        email=email,
        password=hash_password(req.password),
        nickname=(req.nickname or username).strip()[:50],
        phone=phone or None,
    )
    db.add(user)
    try:
        db.flush()
        grant_welcome_coupon(db, user, commit=False)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="用户名或邮箱已被注册")
    db.refresh(user)
    return {
        "code": 200,
        "msg": "注册成功，新人优惠券已到账（7 天内有效）",
        "data": auth_payload_for(user),
    }


@app.post("/api/login")
def login(req: LoginReq, request: Request, db: Session = Depends(get_db)):
    username = (req.username or "").strip()
    ip = request.client.host if request.client else None
    try:
        check_login_rate_limit(username, ip)
    except HTTPException as exc:
        if exc.status_code == 429:
            alert_login_attack(db, ip)
        raise

    user = db.query(User).filter(User.username == username).first()
    if user is None or not verify_password(req.password, user.password or ""):
        record_login_failure(username, ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if int(getattr(user, "is_disabled", 0) or 0) == 1:
        raise HTTPException(status_code=403, detail="账号已禁用，请联系管理员")

    # 旧明文密码登录成功后自动升级为 bcrypt
    if not is_hashed_password(user.password or ""):
        user.password = hash_password(req.password)
        db.commit()
        db.refresh(user)

    clear_login_failures(username, ip)
    note_remote_login(db, user, ip)
    db.refresh(user)
    return {
        "code": 200,
        "msg": "登录成功",
        "data": auth_payload_for(user),
    }


@app.post("/api/sms/send")
def sms_send(req: SmsSendReq, db: Session = Depends(get_db)):
    scene = (req.scene or "").strip()
    if scene not in CODE_SCENES:
        raise HTTPException(status_code=400, detail="该场景不发送验证码短信")
    phone = normalize_phone(req.phone)
    if scene == "admin_mfa":
        raise HTTPException(status_code=400, detail="管理员二次验证请在登录后从后台发送")
    if scene == "phone_login":
        target = user_by_phone(db, phone)
        if target is None:
            raise HTTPException(status_code=404, detail="该手机号尚未绑定账号")
        if int(getattr(target, "is_admin", 0) or 0) == 1:
            raise HTTPException(
                status_code=403,
                detail="管理员禁止只用短信登录，请使用账号密码，进入后台时再做短信二次验证",
            )
    if scene == "register" and user_by_phone(db, phone) is not None:
        raise HTTPException(status_code=400, detail="该手机号已绑定其他账号")
    if scene == "reset_password" and user_by_phone(db, phone) is None:
        raise HTTPException(status_code=404, detail="该手机号尚未绑定账号")
    data = send_code(db, phone, scene)
    return {"code": 200, "msg": "验证码已发送", "data": data}


@app.post("/api/email/send")
def email_send(req: EmailSendReq, db: Session = Depends(get_db)):
    scene = (req.scene or "").strip()
    if scene not in EMAIL_SCENES:
        raise HTTPException(status_code=400, detail="该场景不发送邮箱验证码")
    email = normalize_email(req.email)
    if scene == "admin_mfa":
        raise HTTPException(status_code=400, detail="管理员二次验证请在登录后从后台发送")
    if scene == "email_login":
        target = user_by_email(db, email)
        if target is None:
            raise HTTPException(status_code=404, detail="该邮箱尚未注册")
        if int(getattr(target, "is_admin", 0) or 0) == 1:
            raise HTTPException(
                status_code=403,
                detail="管理员禁止只用邮箱验证码登录，请使用账号密码，进入后台再做二次验证",
            )
    if scene == "register" and user_by_email(db, email) is not None:
        raise HTTPException(status_code=400, detail="该邮箱已被注册")
    if scene == "reset_password" and user_by_email(db, email) is None:
        raise HTTPException(status_code=404, detail="该邮箱尚未注册")
    data = send_email_code(db, email, scene)
    return {"code": 200, "msg": "验证码已发送到邮箱", "data": data}


@app.post("/api/login/phone")
def login_by_phone(req: PhoneLoginReq, request: Request, db: Session = Depends(get_db)):
    phone = normalize_phone(req.phone)
    ip = request.client.host if request.client else None
    try:
        check_login_rate_limit(phone, ip)
    except HTTPException as exc:
        if exc.status_code == 429:
            alert_login_attack(db, ip)
        raise
    user = user_by_phone(db, phone)
    if user is None:
        record_login_failure(phone, ip)
        raise HTTPException(status_code=401, detail="手机号或验证码错误")
    if int(getattr(user, "is_admin", 0) or 0) == 1:
        raise HTTPException(
            status_code=403,
            detail="管理员禁止只用短信登录，请使用账号密码，进入后台时再做短信二次验证",
        )
    if int(getattr(user, "is_disabled", 0) or 0) == 1:
        raise HTTPException(status_code=403, detail="账号已禁用，请联系管理员")
    try:
        verify_code(db, phone, "phone_login", req.sms_code)
    except HTTPException:
        record_login_failure(phone, ip)
        raise
    clear_login_failures(phone, ip)
    note_remote_login(db, user, ip)
    db.refresh(user)
    return {"code": 200, "msg": "登录成功", "data": auth_payload_for(user)}


@app.post("/api/login/email")
def login_by_email(req: EmailLoginReq, request: Request, db: Session = Depends(get_db)):
    email = normalize_email(req.email)
    ip = request.client.host if request.client else None
    try:
        check_login_rate_limit(email, ip)
    except HTTPException as exc:
        if exc.status_code == 429:
            alert_login_attack(db, ip)
        raise
    user = user_by_email(db, email)
    if user is None:
        record_login_failure(email, ip)
        raise HTTPException(status_code=401, detail="邮箱或验证码错误")
    if int(getattr(user, "is_admin", 0) or 0) == 1:
        raise HTTPException(
            status_code=403,
            detail="管理员禁止只用邮箱验证码登录，请使用账号密码，进入后台再做二次验证",
        )
    if int(getattr(user, "is_disabled", 0) or 0) == 1:
        raise HTTPException(status_code=403, detail="账号已禁用，请联系管理员")
    try:
        verify_email_code(db, email, "email_login", req.email_code)
    except HTTPException:
        record_login_failure(email, ip)
        raise
    clear_login_failures(email, ip)
    note_remote_login(db, user, ip)
    db.refresh(user)
    return {"code": 200, "msg": "登录成功", "data": auth_payload_for(user)}


@app.post("/api/password/reset")
def reset_password(req: ResetPasswordReq, db: Session = Depends(get_db)):
    # 优先邮箱重置（个人可用）；兼容旧手机短信重置
    if (req.email or "").strip():
        email = normalize_email(req.email)
        user = user_by_email(db, email)
        if user is None:
            raise HTTPException(status_code=404, detail="该邮箱尚未注册")
        if int(getattr(user, "is_admin", 0) or 0) == 1:
            raise HTTPException(status_code=403, detail="管理员请联系另一名管理员重置")
        verify_email_code(db, email, "reset_password", req.email_code or req.sms_code)
        user.password = hash_password(req.new_password)
        db.commit()
        return {"code": 200, "msg": "密码已重置，请使用新密码登录"}

    phone = normalize_phone(req.phone)
    user = user_by_phone(db, phone)
    if user is None:
        raise HTTPException(status_code=404, detail="该手机号尚未绑定账号")
    if int(getattr(user, "is_admin", 0) or 0) == 1:
        raise HTTPException(status_code=403, detail="管理员不能只用短信重置密码，请联系另一名管理员")
    verify_code(db, phone, "reset_password", req.sms_code)
    user.password = hash_password(req.new_password)
    db.commit()
    return {"code": 200, "msg": "密码已重置，请使用新密码登录"}


@app.post("/api/users/phone/bind")
def bind_phone(
    req: BindPhoneReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    phone = assert_phone_free(db, req.phone, except_user_id=auth.id)
    verify_code(db, phone, "bind_phone", req.sms_code)
    old = (auth.phone or "").strip()
    auth.phone = phone
    db.commit()
    if old and old != phone:
        from sms_service import send_notice

        send_notice(
            db,
            old,
            "phone_changed",
            "你的账号手机号已更换。如非本人操作，请尽快联系管理员。",
            user_id=auth.id,
        )
    db.refresh(auth)
    return {"code": 200, "msg": "手机号已绑定", "data": auth_payload_for(auth)}


@app.get("/api/sms/mine")
def my_sms(
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    phone = (auth.phone or "").strip()
    if phone:
        rows = (
            db.query(SmsLog)
            .filter(or_(SmsLog.user_id == auth.id, SmsLog.phone == phone))
            .order_by(SmsLog.id.desc())
            .limit(20)
            .all()
        )
    else:
        rows = (
            db.query(SmsLog)
            .filter(SmsLog.user_id == auth.id)
            .order_by(SmsLog.id.desc())
            .limit(20)
            .all()
        )
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "kind": r.kind,
                "scene": r.scene,
                "content": r.content if r.kind == "notice" else "验证码短信（内容不回显）",
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
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
            "phone": user.phone or "",
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


@app.get("/api/map/config")
def map_config(auth: User = Depends(get_current_user)):
    """前端 JS Key + 是否已开通实时检索。"""
    key = (os.getenv("AMAP_JS_KEY") or os.getenv("VITE_AMAP_KEY") or "").strip()
    return {
        "code": 200,
        "data": {
            "amap_js_key": key,
            "security_js_code": (os.getenv("AMAP_SECURITY_JS_CODE") or "").strip(),
            "places": list_places(),
            "realtime": realtime_enabled(),
        },
    }


@app.get("/api/map/places")
def map_places(auth: User = Depends(get_current_user)):
    return {"code": 200, "data": list_places()}


@app.post("/api/map/geocode")
def map_geocode(
    req: MapGeocodeReq,
    auth: User = Depends(get_current_user),
):
    """内置坐标优先；未命中则用高德 Web服务实时检索（需 AMAP_WEB_KEY）。"""
    try:
        point = geocode_place(req.place)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"code": 200, "msg": "定位成功", "data": point}


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
    fb_map = {
        f.message_id: f.rating
        for f in db.query(ChatFeedback)
        .filter(
            ChatFeedback.user_id == user_id,
            ChatFeedback.message_id.in_([r.id for r in rows] or [-1]),
        )
        .all()
    }
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "my_rating": fb_map.get(r.id),
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

    map_point = parse_map_marker(answer)
    maps = parse_all_map_markers(answer)
    last_ai = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conv_id,
            ChatMessage.role == "ai",
        )
        .order_by(ChatMessage.id.desc())
        .first()
    )
    return {
        "code": 200,
        "msg": "调用成功",
        "data": {
            "answer": answer,
            "conversation_id": conv_id,
            "map": map_point,
            "maps": maps,
            "message_id": last_ai.id if last_ai else None,
        },
    }


class FeedbackReq(BaseModel):
    user_id: int
    message_id: int
    rating: str  # up | down
    comment: str = ""


class KnowledgeCreateReq(BaseModel):
    title: str
    content: str
    category: str = "业务资料"


@app.post("/api/feedback")
def submit_feedback(
    req: FeedbackReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    assert_self_or_admin(auth, req.user_id)
    rating = (req.rating or "").strip().lower()
    if rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating 只能是 up 或 down")
    msg = db.get(ChatMessage, req.message_id)
    if msg is None or msg.role != "ai":
        raise HTTPException(status_code=404, detail="消息不存在")
    if msg.user_id != req.user_id and not auth.is_admin:
        # 消息归属会话用户：ChatMessage.user_id 为发送对话的用户
        pass
    row = (
        db.query(ChatFeedback)
        .filter(
            ChatFeedback.message_id == req.message_id,
            ChatFeedback.user_id == req.user_id,
        )
        .first()
    )
    if row is None:
        row = ChatFeedback(
            message_id=req.message_id,
            conversation_id=msg.conversation_id,
            user_id=req.user_id,
            rating=rating,
            comment=(req.comment or "").strip()[:500],
            handle_status="pending",
            issue_tag="",
        )
        db.add(row)
    else:
        row.rating = rating
        row.comment = (req.comment or "").strip()[:500]
    db.commit()
    return {"code": 200, "msg": "已记录反馈", "data": {"rating": rating}}


def _feedback_row(db: Session, f: ChatFeedback) -> dict:
    msg = db.get(ChatMessage, f.message_id)
    user = db.get(User, f.user_id)
    return {
        "id": f.id,
        "rating": f.rating,
        "comment": f.comment or "",
        "handle_status": getattr(f, "handle_status", None) or "pending",
        "issue_tag": getattr(f, "issue_tag", None) or "",
        "user_id": f.user_id,
        "username": user.username if user else "",
        "nickname": (user.nickname if user else "") or "",
        "message_id": f.message_id,
        "conversation_id": f.conversation_id,
        "content_preview": (msg.content or "")[:160] if msg else "",
        "created_at": f.created_at.isoformat() if f.created_at else "",
    }


class AdminFeedbackUpdateReq(BaseModel):
    comment: str | None = None
    handle_status: str | None = None
    issue_tag: str | None = None


class AdminFeedbackBatchReq(BaseModel):
    ids: list[int] = Field(default_factory=list)
    handle_status: str = "processing"


@app.get("/api/admin/feedback")
def admin_feedback(
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    rows = (
        db.query(ChatFeedback)
        .order_by(ChatFeedback.id.desc())
        .limit(300)
        .all()
    )
    return {"code": 200, "data": [_feedback_row(db, f) for f in rows]}


@app.post("/api/admin/feedback/{feedback_id}/update")
def admin_feedback_update(
    feedback_id: int,
    req: AdminFeedbackUpdateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    row = db.get(ChatFeedback, feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if req.comment is not None:
        row.comment = (req.comment or "").strip()[:500]
    if req.handle_status is not None:
        status = (req.handle_status or "").strip().lower()
        if status not in ("pending", "processing", "resolved"):
            raise HTTPException(status_code=400, detail="处理状态无效")
        row.handle_status = status
    if req.issue_tag is not None:
        tag = (req.issue_tag or "").strip().lower()
        if tag and tag not in ("hallucination", "kb_missing", "bug", "other"):
            raise HTTPException(status_code=400, detail="问题标签无效")
        row.issue_tag = tag
    db.commit()
    db.refresh(row)
    return {"code": 200, "msg": "已更新", "data": _feedback_row(db, row)}


@app.post("/api/admin/feedback/batch")
def admin_feedback_batch(
    req: AdminFeedbackBatchReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    status = (req.handle_status or "").strip().lower()
    if status not in ("pending", "processing", "resolved"):
        raise HTTPException(status_code=400, detail="处理状态无效")
    ids = sorted({int(i) for i in (req.ids or []) if int(i) > 0})
    if not ids:
        raise HTTPException(status_code=400, detail="请选择反馈")
    rows = db.query(ChatFeedback).filter(ChatFeedback.id.in_(ids)).all()
    for row in rows:
        row.handle_status = status
    db.commit()
    return {"code": 200, "msg": f"已更新 {len(rows)} 条", "data": {"count": len(rows)}}


@app.get("/api/admin/feedback/{feedback_id}/context")
def admin_feedback_context(
    feedback_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    row = db.get(ChatFeedback, feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    conv_id = int(row.conversation_id or 0)
    msgs = []
    if conv_id > 0:
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv_id)
            .order_by(ChatMessage.id.asc())
            .limit(80)
            .all()
        )
    else:
        target = db.get(ChatMessage, row.message_id)
        if target is not None:
            msgs = (
                db.query(ChatMessage)
                .filter(ChatMessage.conversation_id == target.conversation_id)
                .order_by(ChatMessage.id.asc())
                .limit(80)
                .all()
            )
    return {
        "code": 200,
        "data": {
            "feedback": _feedback_row(db, row),
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else "",
                    "is_target": m.id == row.message_id,
                }
                for m in msgs
            ],
        },
    }


@app.get("/api/knowledge/categories")
def knowledge_categories(auth: User = Depends(get_current_user)):
    return {"code": 200, "data": KB_CATEGORIES}


@app.get("/api/knowledge/docs")
def knowledge_docs(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    rows = list_docs(db, category)
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "category": r.category,
                "title": r.title,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.post("/api/knowledge/docs")
def knowledge_create(
    req: KnowledgeCreateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    """共享知识库仅管理员可写入（普通用户通过对话自动引用）。"""
    require_admin(auth)
    cat = (req.category or "").strip()
    if cat not in KB_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"分类必须是：{' / '.join(KB_CATEGORIES)}",
        )
    title = (req.title or "").strip()
    content = (req.content or "").strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="标题和内容不能为空")
    row = KnowledgeDoc(
        category=cat,
        title=title[:200],
        content=content,
        user_id=auth.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "code": 200,
        "msg": "已保存",
        "data": {"id": row.id, "category": row.category, "title": row.title},
    }


@app.post("/api/knowledge/docs/{doc_id}/remove")
def knowledge_remove(
    doc_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    row = db.get(KnowledgeDoc, doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    db.delete(row)
    db.commit()
    return {"code": 200, "msg": "已删除"}


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
    channel: str = "alipay"  # alipay | wechat
    sms_code: str = ""
    coupon_code: str = ""


class OrderActionReq(BaseModel):
    user_id: int
    sms_code: str = ""


class AdminGrantVipReq(BaseModel):
    admin_user_id: int
    user_id: int
    days: int = 30
    package_id: str = ""


class AdminBatchGrantVipReq(BaseModel):
    admin_user_id: int = 0
    user_ids: list[int] = Field(default_factory=list)
    days: int = 30
    package_id: str = ""


class AdminRevokeVipReq(BaseModel):
    admin_user_id: int
    user_id: int


def _write_admin_log(
    db: Session,
    admin: User,
    *,
    action: str,
    detail: str,
    target: User | None = None,
) -> None:
    db.add(
        AdminOpLog(
            admin_user_id=int(admin.id),
            admin_username=admin.username or "",
            action=action,
            target_user_id=int(target.id) if target else None,
            target_username=(target.username if target else "") or "",
            detail=(detail or "")[:500],
        )
    )


@app.get("/api/vip/packages")
def vip_packages():
    ali = alipay_configured()
    wx = wechat_configured()
    return {
        "code": 200,
        "data": {
            "packages": list_public_packages(),
            "coupons": list_campaign_coupons(),
            "features": VIP_FEATURE_LABELS,
            "pay_ready": ali or wx,
            "pay_channel": "alipay",
            "channels": {
                "alipay": ali,
                "wechat": wx,
            },
            "refund_note": "虚拟会员服务开通后不支持无理由退款；支付异常请在个人中心「联系客服」提交工单。",
            "coupon_rules": "新人注册自动获赠 APEX5；APEX10 可在个人中心领取一次；客服补偿券由工单处理后赠送。",
        },
    }


class CouponClaimReq(BaseModel):
    code: str


@app.get("/api/vip/coupons/mine")
def vip_coupons_mine(
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    return {
        "code": 200,
        "data": {
            "mine": list_user_coupons(db, auth),
            "campaign": list_campaign_coupons(),
            "rules": "注册送 APEX5；活动券 APEX10 可领 1 次；客服可另赠补偿券。券有有效期，每人每张限用 1 次。",
        },
    }


@app.post("/api/vip/coupons/claim")
def vip_coupons_claim(
    req: CouponClaimReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    try:
        row = claim_coupon(db, auth, req.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "code": 200,
        "msg": f"已领取 {row.coupon_code}，请在有效期内使用",
        "data": list_user_coupons(db, auth),
    }


SUPPORT_CATEGORIES = {
    "pay": "支付/订单异常",
    "vip": "VIP/权益问题",
    "bug": "功能故障",
    "account": "账号安全",
    "other": "其他",
}


class SupportCreateReq(BaseModel):
    category: str = "other"
    title: str = ""
    content: str


class SupportAdminUpdateReq(BaseModel):
    status: str | None = None
    admin_reply: str | None = None
    grant_coupon: str | None = None  # COMP5 / COMP10 / COMP20


class AdminGrantCouponReq(BaseModel):
    user_id: int
    template: str = "COMP10"
    note: str = ""
    ticket_id: int | None = None


def _ticket_dict(db: Session, t: SupportTicket) -> dict:
    user = db.get(User, t.user_id)
    return {
        "id": t.id,
        "user_id": t.user_id,
        "username": user.username if user else "",
        "nickname": (user.nickname if user else "") or "",
        "category": t.category,
        "category_label": SUPPORT_CATEGORIES.get(t.category, t.category),
        "title": t.title or "",
        "content": t.content or "",
        "status": t.status,
        "admin_reply": t.admin_reply or "",
        "granted_coupon_code": t.granted_coupon_code or "",
        "admin_user_id": t.admin_user_id,
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else "",
    }


@app.get("/api/support/categories")
def support_categories():
    return {
        "code": 200,
        "data": [{"value": k, "label": v} for k, v in SUPPORT_CATEGORIES.items()],
    }


@app.post("/api/support/tickets")
def support_create(
    req: SupportCreateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    cat = (req.category or "other").strip().lower()
    if cat not in SUPPORT_CATEGORIES:
        raise HTTPException(status_code=400, detail="问题类型无效")
    content = (req.content or "").strip()
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="请至少说明 5 个字的问题详情")
    title = (req.title or "").strip()[:120]
    if not title:
        title = content[:40]
    open_n = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.user_id == auth.id,
            SupportTicket.status.in_(("pending", "processing")),
        )
        .count()
    )
    if open_n >= 5:
        raise HTTPException(status_code=400, detail="未结工单过多，请等待客服处理后再提交")
    row = SupportTicket(
        user_id=auth.id,
        category=cat,
        title=title,
        content=content[:2000],
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"code": 200, "msg": "已提交，客服将尽快回复", "data": _ticket_dict(db, row)}


@app.get("/api/support/tickets/mine")
def support_my_tickets(
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    rows = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == auth.id)
        .order_by(SupportTicket.id.desc())
        .limit(50)
        .all()
    )
    return {"code": 200, "data": [_ticket_dict(db, r) for r in rows]}


@app.get("/api/admin/support/tickets")
def admin_support_list(
    status: str = "",
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    q = db.query(SupportTicket)
    st = (status or "").strip().lower()
    if st in ("pending", "processing", "resolved", "closed"):
        q = q.filter(SupportTicket.status == st)
    rows = q.order_by(SupportTicket.id.desc()).limit(300).all()
    return {
        "code": 200,
        "data": {
            "tickets": [_ticket_dict(db, r) for r in rows],
            "grantable_coupons": list_grantable_coupons(),
            "categories": SUPPORT_CATEGORIES,
        },
    }


@app.post("/api/admin/support/tickets/{ticket_id}/update")
def admin_support_update(
    ticket_id: int,
    req: SupportAdminUpdateReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    row = db.get(SupportTicket, ticket_id)
    if row is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    user = _user_or_404(db, row.user_id)
    if req.admin_reply is not None:
        row.admin_reply = (req.admin_reply or "").strip()[:2000]
    if req.status is not None:
        st = (req.status or "").strip().lower()
        if st not in ("pending", "processing", "resolved", "closed"):
            raise HTTPException(status_code=400, detail="状态无效")
        row.status = st
    granted = ""
    if (req.grant_coupon or "").strip():
        try:
            coupon = grant_support_coupon(
                db,
                user,
                req.grant_coupon.strip(),
                ticket_id=row.id,
                note=f"工单#{row.id}补偿",
                commit=False,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        granted = coupon.coupon_code
        row.granted_coupon_code = granted
        if not row.status or row.status in ("pending", "processing"):
            row.status = "resolved"
        if not (row.admin_reply or "").strip():
            row.admin_reply = f"已为您赠送补偿优惠券 {granted}，请在个人中心优惠券中查看使用。"
        _write_admin_log(
            db,
            auth,
            action="grant_coupon",
            target=user,
            detail=f"工单#{row.id} 赠券 {granted}",
        )
        notify_user(
            db,
            user,
            "support_coupon",
            f"客服已处理你的工单#{row.id}，并赠送优惠券 {granted}。",
        )
    row.admin_user_id = auth.id
    db.commit()
    db.refresh(row)
    msg = "已更新工单"
    if granted:
        msg = f"已回复并赠送优惠券 {granted}"
    return {"code": 200, "msg": msg, "data": _ticket_dict(db, row)}


@app.post("/api/admin/coupons/grant")
def admin_coupons_grant(
    req: AdminGrantCouponReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    """管理员直接给用户赠送补偿券（可不经工单）。"""
    require_admin_mfa(auth)
    user = _user_or_404(db, req.user_id)
    try:
        row = grant_support_coupon(
            db,
            user,
            req.template,
            ticket_id=req.ticket_id,
            note=(req.note or "管理员赠送")[:200],
            commit=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _write_admin_log(
        db,
        auth,
        action="grant_coupon",
        target=user,
        detail=f"直接赠券 {row.coupon_code}",
    )
    notify_user(db, user, "support_coupon", f"管理员为你赠送了优惠券 {row.coupon_code}，请在个人中心查看。")
    return {
        "code": 200,
        "msg": f"已赠送 {row.coupon_code}",
        "data": {"coupon": list_user_coupons(db, user)[0], "code": row.coupon_code},
    }


@app.get("/api/admin/coupons/templates")
def admin_coupon_templates(auth: User = Depends(get_current_user)):
    require_admin(auth)
    return {"code": 200, "data": list_grantable_coupons()}


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
    """创建 VIP 订单并返回支付宝跳转链接或微信扫码 code_url。"""
    assert_self_or_admin(auth, req.user_id)
    user = _user_or_404(db, req.user_id)
    try:
        order, pay = create_vip_order(
            db,
            user,
            req.package_id,
            channel=req.channel or "alipay",
            coupon_code=req.coupon_code or "",
        )
    except (PaymentConfigError, WechatPaymentConfigError) as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ch = pay.get("channel") or order.channel
    msg = "请用微信扫码支付" if ch == "wechat" else "请完成支付宝支付"
    return {
        "code": 200,
        "msg": f"订单已创建，{msg}",
        "data": {
            "order_id": order.id,
            "out_trade_no": order.out_trade_no,
            "package_name": order.package_name,
            "amount": order.amount,
            "days": order.days,
            "status": order.status,
            "channel": ch,
            "pay_url": pay.get("pay_url") or "",
            "code_url": pay.get("code_url") or "",
            "pay_ready": alipay_configured() or wechat_configured(),
        },
    }


def _order_public_dict(r: RechargeOrder) -> dict:
    return {
        "id": r.id,
        "out_trade_no": r.out_trade_no or "",
        "package_id": r.package_id or "",
        "package_name": r.package_name,
        "amount": r.amount,
        "days": r.days,
        "status": r.status,
        "channel": r.channel or "",
        "remark": r.remark or "",
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


def _is_test_order(r: RechargeOrder) -> bool:
    pid = (r.package_id or "").strip().lower()
    name = r.package_name or ""
    return pid == "vip_test" or "支付测试" in name or "1分钱" in name


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
    if _is_test_order(order) and not auth.is_admin:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"code": 200, "data": _order_public_dict(order)}


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
    # 取消待支付订单时释放占用中的优惠券
    from coupon_service import release_coupon

    linked = (
        db.query(UserCoupon)
        .filter(UserCoupon.order_id == order.id, UserCoupon.user_id == order.user_id)
        .first()
    )
    if linked is not None:
        release_coupon(db, linked)
    db.commit()
    return {"code": 200, "msg": "订单已取消"}


@app.post("/api/vip/orders/{order_id}/pay")
def vip_continue_pay(
    order_id: int,
    req: OrderActionReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    """待支付订单重新生成支付参数（支付宝跳转或微信扫码）。"""
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
        pay = rebuild_pay_payload(order)
    except (PaymentConfigError, WechatPaymentConfigError) as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    ch = pay.get("channel") or order.channel
    msg = "请用微信扫码支付" if ch == "wechat" else "请完成支付宝支付"
    return {
        "code": 200,
        "msg": msg,
        "data": {
            "order_id": order.id,
            "channel": ch,
            "pay_url": pay.get("pay_url") or "",
            "code_url": pay.get("code_url") or "",
        },
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
            channel="alipay",
        )
    return PlainTextResponse("success")


@app.post("/api/pay/wechat/notify")
async def wechat_notify(request: Request, db: Session = Depends(get_db)):
    """微信支付结果通知。"""
    try:
        payload = await request.json()
        resource = payload.get("resource") or {}
        data = decrypt_notify_resource(resource)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"code": "FAIL", "message": "解密失败"},
        )
    if data.get("trade_state") == "SUCCESS":
        mark_order_paid(
            db,
            data.get("out_trade_no", ""),
            trade_no=data.get("transaction_id", ""),
            channel="wechat",
        )
    return JSONResponse(content={"code": "SUCCESS", "message": "成功"})


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
        .limit(100)
        .all()
    )
    # 用户前台隐藏「支付测试（1分钱）」订单
    visible = [r for r in rows if not _is_test_order(r)]
    return {"code": 200, "data": [_order_public_dict(r) for r in visible]}


def _require_pay_sms(db: Session, user: User, sms_code: str) -> None:
    email = (getattr(user, "email", None) or "").strip()
    phone = (getattr(user, "phone", None) or "").strip()
    if email:
        verify_email_code(db, email, "pay_confirm", sms_code)
        return
    if not phone:
        raise HTTPException(status_code=400, detail="下单前请确认邮箱可用，或绑定手机号完成验证")
    verify_code(db, phone, "pay_confirm", sms_code)


def _sms_row(r: SmsLog) -> dict:
    return {
        "id": r.id,
        "phone": mask_phone(r.phone) if r.phone else "未绑定手机",
        "kind": r.kind,
        "scene": r.scene,
        "content": r.content if r.kind == "notice" else "验证码短信",
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


@app.get("/api/admin/mfa/status")
def admin_mfa_status(auth: User = Depends(get_current_user)):
    require_admin(auth)
    until = getattr(auth, "admin_mfa_until", None)
    return {
        "code": 200,
        "data": {
            "phone": auth.phone or "",
            "phone_bound": bool((auth.phone or "").strip()),
            "email": mask_email(auth.email),
            "email_bound": bool((auth.email or "").strip()),
            "channel": "email" if (auth.email or "").strip() else "sms",
            "smtp_ready": email_configured(),
            "mfa_valid": mfa_active(auth),
            "mfa_until": until.isoformat() if until else "",
        },
    }


@app.post("/api/admin/mfa/send")
def admin_mfa_send(
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    email = (auth.email or "").strip()
    phone = (auth.phone or "").strip()
    # 优先邮箱（个人可真收）；无邮箱再走短信
    if email:
        data = send_email_code(db, email, "admin_mfa", user_id=auth.id)
        return {"code": 200, "msg": "二次验证码已发送到邮箱", "data": data}
    if not phone:
        raise HTTPException(status_code=400, detail="请先完善账号邮箱，或绑定手机号后再做二次验证")
    data = send_code(db, phone, "admin_mfa", user_id=auth.id)
    return {"code": 200, "msg": "二次验证码已发送", "data": data}


@app.post("/api/admin/mfa/verify")
def admin_mfa_verify(
    req: AdminMfaReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin(auth)
    email = (auth.email or "").strip()
    phone = (auth.phone or "").strip()
    if email:
        verify_email_code(db, email, "admin_mfa", req.sms_code)
    elif phone:
        verify_code(db, phone, "admin_mfa", req.sms_code)
    else:
        raise HTTPException(status_code=400, detail="请先完善邮箱或绑定手机号")
    until = grant_admin_mfa(db, auth)
    return {
        "code": 200,
        "msg": "二次验证通过，30 分钟内可进入后台",
        "data": {"mfa_until": until.isoformat()},
    }


@app.get("/api/admin/users")
def admin_list_users(
    admin_user_id: int = 0,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    rows = db.query(User).order_by(User.id.desc()).limit(200).all()
    return {
        "code": 200,
        "data": [
            {
                "user_id": u.id,
                "username": u.username,
                "nickname": u.nickname or u.username,
                "email": u.email,
                "phone": mask_phone(u.phone),
                "is_disabled": bool(int(getattr(u, "is_disabled", 0) or 0)),
                "quota_chat_extra": int(getattr(u, "quota_chat_extra", 0) or 0),
                "quota_image_extra": int(getattr(u, "quota_image_extra", 0) or 0),
                **vip_status(u),
            }
            for u in rows
        ],
    }


def _resolve_grant_days(days: int, package_id: str = "") -> tuple[int, str]:
    pkg = get_package(package_id) if package_id else None
    if pkg:
        return int(pkg["days"]), str(pkg["name"])
    d = max(1, int(days or 30))
    return d, f"自定义 {d} 天"


@app.post("/api/admin/vip/grant")
def admin_grant_vip(
    req: AdminGrantVipReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    user = _user_or_404(db, req.user_id)
    days, pkg_name = _resolve_grant_days(req.days, req.package_id)
    extend_vip(user, days)
    _write_admin_log(
        db,
        auth,
        action="grant_vip",
        target=user,
        detail=f"开通/续期 VIP {days} 天（{pkg_name}）",
    )
    db.commit()
    db.refresh(user)
    notify_vip_opened(db, user, pkg_name, days)
    notify_admin_risk(db, auth, f"手动开通会员：用户 {user.username}，{days} 天")
    return {"code": 200, "msg": f"已开通 {days} 天 VIP", "data": vip_status(user)}


@app.post("/api/admin/vip/grant-batch")
def admin_grant_vip_batch(
    req: AdminBatchGrantVipReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    ids = sorted({int(i) for i in (req.user_ids or []) if int(i) > 0})
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要开通的用户")
    days, pkg_name = _resolve_grant_days(req.days, req.package_id)
    rows = db.query(User).filter(User.id.in_(ids)).all()
    if not rows:
        raise HTTPException(status_code=404, detail="未找到用户")
    for user in rows:
        extend_vip(user, days)
        _write_admin_log(
            db,
            auth,
            action="batch_grant_vip",
            target=user,
            detail=f"批量开通 VIP {days} 天（{pkg_name}）",
        )
        notify_vip_opened(db, user, pkg_name, days)
    _write_admin_log(
        db,
        auth,
        action="batch_grant_vip_summary",
        detail=f"批量开通 {len(rows)} 人 VIP {days} 天（{pkg_name}）",
    )
    db.commit()
    notify_admin_risk(
        db, auth, f"批量开通会员：{len(rows)} 人，{days} 天（{pkg_name}）"
    )
    return {
        "code": 200,
        "msg": f"已为 {len(rows)} 名用户开通 {days} 天 VIP",
        "data": {"count": len(rows), "days": days},
    }


@app.post("/api/admin/vip/revoke")
def admin_revoke_vip(
    req: AdminRevokeVipReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    user = _user_or_404(db, req.user_id)
    revoke_vip(user)
    _write_admin_log(
        db,
        auth,
        action="revoke_vip",
        target=user,
        detail="取消 VIP",
    )
    db.commit()
    db.refresh(user)
    notify_user(db, user, "vip_opened", "会员状态变更：你的 VIP 已被管理员取消。")
    notify_admin_risk(db, auth, f"取消会员：用户 {user.username}")
    return {"code": 200, "msg": "已取消 VIP", "data": vip_status(user)}


@app.get("/api/admin/users/{user_id}")
def admin_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    user = _user_or_404(db, user_id)
    orders = (
        db.query(RechargeOrder)
        .filter(RechargeOrder.user_id == user_id)
        .order_by(RechargeOrder.id.desc())
        .limit(50)
        .all()
    )
    logs = (
        db.query(AdminOpLog)
        .filter(AdminOpLog.target_user_id == user_id)
        .order_by(AdminOpLog.id.desc())
        .limit(50)
        .all()
    )
    return {
        "code": 200,
        "data": {
            "user": {
                "user_id": user.id,
                "username": user.username,
                "nickname": user.nickname or user.username,
                "email": user.email,
                "phone": mask_phone(user.phone),
                "created_at": user.created_at.isoformat() if user.created_at else "",
                **vip_status(user),
            },
            "orders": [
                {
                    "id": r.id,
                    "out_trade_no": r.out_trade_no,
                    "package_name": r.package_name,
                    "amount": r.amount,
                    "days": r.days,
                    "status": r.status,
                    "channel": r.channel,
                    "remark": r.remark,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in orders
            ],
            "vip_history": [
                {
                    "id": log.id,
                    "action": log.action,
                    "detail": log.detail,
                    "admin_username": log.admin_username,
                    "created_at": log.created_at.isoformat() if log.created_at else "",
                }
                for log in logs
            ],
        },
    }


@app.get("/api/admin/op-logs")
def admin_op_logs(
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    rows = (
        db.query(AdminOpLog)
        .order_by(AdminOpLog.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "code": 200,
        "data": [
            {
                "id": r.id,
                "admin_user_id": r.admin_user_id,
                "admin_username": r.admin_username,
                "action": r.action,
                "target_user_id": r.target_user_id,
                "target_username": r.target_username,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@app.post("/api/admin/users/disable")
def admin_disable_user(
    req: AdminDisableReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    user = _user_or_404(db, req.user_id)
    if int(user.id) == int(auth.id):
        raise HTTPException(status_code=400, detail="不能禁用自己的管理员账号")
    user.is_disabled = 1 if req.disabled else 0
    db.commit()
    action = "禁用用户账号" if req.disabled else "启用用户账号"
    notify_user(db, user, "admin_risk", f"账号安全通知：你的账号已被管理员{action.replace('用户账号', '')}。")
    notify_admin_risk(db, auth, f"{action}：{user.username}")
    return {"code": 200, "msg": f"已{action} {user.username}"}


@app.post("/api/admin/users/reset-password")
def admin_reset_password(
    req: AdminResetPasswordReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    user = _user_or_404(db, req.user_id)
    user.password = hash_password(req.new_password)
    db.commit()
    notify_user(db, user, "admin_risk", "账号安全通知：管理员已重置你的登录密码。如非本人申请，请尽快联系客服。")
    notify_admin_risk(db, auth, f"重置他人密码：{user.username}")
    return {"code": 200, "msg": f"已重置 {user.username} 的密码"}


@app.post("/api/admin/users/quota")
def admin_set_quota(
    req: AdminQuotaReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    ids = [int(i) for i in req.user_ids if int(i) > 0]
    if not ids:
        raise HTTPException(status_code=400, detail="请选择要调整额度的用户")
    chat_extra = max(0, int(req.chat_extra))
    image_extra = max(0, int(req.image_extra))
    rows = db.query(User).filter(User.id.in_(ids)).all()
    for user in rows:
        user.quota_chat_extra = chat_extra
        user.quota_image_extra = image_extra
    db.commit()
    notify_admin_risk(
        db,
        auth,
        f"批量修改用户额度：{len(rows)} 人，对话 +{chat_extra}，生图 +{image_extra}",
    )
    return {"code": 200, "msg": f"已调整 {len(rows)} 名用户的额外额度"}


@app.post("/api/admin/orders/approve")
def admin_approve_order(
    req: AdminApproveOrderReq,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    order = db.get(RechargeOrder, req.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == "paid":
        return {"code": 200, "msg": "订单已是已支付状态"}
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="只能审核待支付订单")
    user = _user_or_404(db, order.user_id)
    extend_vip(user, order.days)
    order.status = "paid"
    order.remark = f"管理员 {auth.username} 审核开通"
    order.channel = order.channel or "admin"
    _write_admin_log(
        db,
        auth,
        action="approve_order",
        target=user,
        detail=f"审核订单 #{order.id} 并开通 {order.days} 天（{order.package_name}）",
    )
    db.commit()
    notify_vip_opened(db, user, order.package_name, order.days)
    notify_admin_risk(db, auth, f"审核订单并开通会员：订单 {order.id}，用户 {user.username}")
    return {"code": 200, "msg": "订单已审核通过并开通会员"}


@app.get("/api/admin/sms")
def admin_sms_logs(
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
    rows = (
        db.query(SmsLog)
        .filter(SmsLog.kind == "notice")
        .order_by(SmsLog.id.desc())
        .limit(30)
        .all()
    )
    return {"code": 200, "data": [_sms_row(r) for r in rows]}


@app.get("/api/admin/recharges")
def admin_recharges(
    admin_user_id: int = 0,
    db: Session = Depends(get_db),
    auth: User = Depends(get_current_user),
):
    require_admin_mfa(auth)
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
