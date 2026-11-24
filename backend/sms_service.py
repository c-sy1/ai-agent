"""短信：验证码与通知分开。已配阿里云 Dysmsapi 时真发；否则演示模式回显验证码。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import SmsLog, User

load_dotenv()

CODE_TTL = timedelta(minutes=5)
RESEND_GAP = timedelta(seconds=60)
MFA_TTL = timedelta(minutes=30)
MAX_CODE_FAILS = 5

# 带 6 位数字，只用于身份校验
CODE_SCENES = {
    "register": "注册",
    "phone_login": "手机号登录",
    "reset_password": "找回密码",
    "bind_phone": "绑定手机号",
    "pay_confirm": "支付下单确认",
    "admin_mfa": "管理员二次验证",
}

# 不带验证码，只发提醒
NOTICE_SCENES = {
    "vip_opened": "会员开通",
    "remote_login": "异地登录",
    "phone_changed": "手机号变更",
    "admin_risk": "高危操作",
    "system_alert": "系统告警",
}

_last_attack_alert: datetime | None = None


def _reload_sms_env() -> None:
    load_dotenv(override=True)


def sms_configured() -> bool:
    _reload_sms_env()
    return bool(
        (os.getenv("SMS_ACCESS_KEY_ID") or "").strip()
        and (os.getenv("SMS_ACCESS_KEY_SECRET") or "").strip()
        and (os.getenv("SMS_SIGN_NAME") or "").strip()
        and (os.getenv("SMS_TEMPLATE_CODE") or "").strip()
    )


def sms_demo_mode() -> bool:
    _reload_sms_env()
    flag = (os.getenv("SMS_DEMO") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if flag in ("0", "false", "no", "off"):
        return not sms_configured()
    # 没配齐阿里云参数时默认演示
    return not sms_configured()


def _percent_encode(value: str) -> str:
    return quote(str(value), safe="~")


def _aliyun_sign(params: dict, secret: str) -> str:
    items = sorted((k, v) for k, v in params.items() if k != "Signature")
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in items)
    string_to_sign = f"GET&{_percent_encode('/')}&{_percent_encode(canonical)}"
    key = (secret + "&").encode("utf-8")
    digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def _send_aliyun_sms(phone: str, template_code: str, template_param: dict) -> None:
    """调用阿里云短信 SendSms。失败抛 HTTPException。"""
    _reload_sms_env()
    access_key = (os.getenv("SMS_ACCESS_KEY_ID") or "").strip()
    access_secret = (os.getenv("SMS_ACCESS_KEY_SECRET") or "").strip()
    sign_name = (os.getenv("SMS_SIGN_NAME") or "").strip()
    if not (access_key and access_secret and sign_name and template_code):
        raise HTTPException(status_code=503, detail="短信服务未配置完整，请检查 .env")

    params = {
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "AccessKeyId": access_key,
        "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Format": "JSON",
        "Action": "SendSms",
        "Version": "2017-05-25",
        "RegionId": (os.getenv("SMS_REGION_ID") or "cn-hangzhou").strip(),
        "PhoneNumbers": phone,
        "SignName": sign_name,
        "TemplateCode": template_code,
        "TemplateParam": json.dumps(template_param, ensure_ascii=False),
    }
    params["Signature"] = _aliyun_sign(params, access_secret)
    url = "https://dysmsapi.aliyuncs.com/?" + "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in params.items()
    )
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"短信网关请求失败：{e}") from e

    code = str(data.get("Code") or "")
    if code != "OK":
        msg = data.get("Message") or code or "发送失败"
        raise HTTPException(status_code=502, detail=f"短信发送失败：{msg}")


def _dispatch_sms(phone: str, *, kind: str, code: str = "", content: str = "") -> None:
    if sms_demo_mode():
        return
    if kind == "code":
        tpl = (os.getenv("SMS_TEMPLATE_CODE") or "").strip()
        # 模板变量名默认 code；可在 .env 改 SMS_TEMPLATE_PARAM_KEY
        key = (os.getenv("SMS_TEMPLATE_PARAM_KEY") or "code").strip() or "code"
        _send_aliyun_sms(phone, tpl, {key: code})
        return

    # 通知短信：优先专用模板；没有则跳过真发（仍写库便于演示）
    tpl = (os.getenv("SMS_NOTICE_TEMPLATE_CODE") or "").strip()
    if not tpl:
        return
    key = (os.getenv("SMS_NOTICE_PARAM_KEY") or "content").strip() or "content"
    # 通知模板变量通常较短，截断避免超长拒收
    _send_aliyun_sms(phone, tpl, {key: (content or "")[:40]})


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if not re.fullmatch(r"1\d{10}", digits):
        raise HTTPException(status_code=400, detail="请填写 11 位中国大陆手机号")
    return digits


def mask_phone(phone: str | None) -> str:
    p = (phone or "").strip()
    if len(p) < 7:
        return ""
    return f"{p[:3]}****{p[-4:]}"


def _now() -> datetime:
    return datetime.utcnow()


def _latest_code(db: Session, phone: str, scene: str) -> SmsLog | None:
    return (
        db.query(SmsLog)
        .filter(SmsLog.phone == phone, SmsLog.scene == scene, SmsLog.kind == "code")
        .order_by(SmsLog.id.desc())
        .first()
    )


def send_code(db: Session, phone: str, scene: str, user_id: int | None = None) -> dict:
    if scene not in CODE_SCENES:
        raise HTTPException(status_code=400, detail="不支持的验证码场景")
    phone = normalize_phone(phone)
    prev = _latest_code(db, phone, scene)
    if prev and prev.created_at and _now() - prev.created_at < RESEND_GAP and int(prev.used or 0) == 0:
        raise HTTPException(status_code=429, detail="验证码已发送，请 60 秒后再试")

    code = f"{random.randint(0, 999999):06d}"
    label = CODE_SCENES[scene]
    content = f"【Apex AI】验证码 {code}，5 分钟内有效，用于{label}。请勿泄露给他人。"
    row = SmsLog(
        phone=phone,
        user_id=user_id,
        kind="code",
        scene=scene,
        content=content,
        code=code,
        used=0,
        fail_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        _dispatch_sms(phone, kind="code", code=code)
    except HTTPException:
        # 真发失败：作废本条，避免用户用未送达的码
        row.used = 1
        db.commit()
        raise
    data = {
        "phone": mask_phone(phone),
        "scene": scene,
        "kind": "code",
        "demo": sms_demo_mode(),
        "provider": "demo" if sms_demo_mode() else "aliyun",
    }
    if sms_demo_mode():
        data["demo_code"] = code
    return data


def send_notice(
    db: Session,
    phone: str,
    scene: str,
    content: str,
    user_id: int | None = None,
) -> None:
    if scene not in NOTICE_SCENES:
        scene = "system_alert"
    phone = (phone or "").strip()
    text = content.strip()
    if not text.startswith("【"):
        text = f"【Apex AI】{text}"
    row = SmsLog(
        phone=phone,
        user_id=user_id,
        kind="notice",
        scene=scene,
        content=text[:500],
        code="",
        used=1,
    )
    db.add(row)
    db.commit()
    if phone and re.fullmatch(r"1\d{10}", phone):
        try:
            _dispatch_sms(phone, kind="notice", content=text)
        except HTTPException:
            # 通知失败不阻断主流程
            pass


def verify_code(db: Session, phone: str, scene: str, code: str) -> None:
    phone = normalize_phone(phone)
    submitted = (code or "").strip()
    if not re.fullmatch(r"\d{6}", submitted):
        raise HTTPException(status_code=400, detail="请输入 6 位短信验证码")
    row = _latest_code(db, phone, scene)
    if row is None or int(row.used or 0) == 1:
        raise HTTPException(status_code=400, detail="请先获取短信验证码")
    if row.created_at and _now() - row.created_at > CODE_TTL:
        row.used = 1
        db.commit()
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    if int(row.fail_count or 0) >= MAX_CODE_FAILS:
        row.used = 1
        db.commit()
        raise HTTPException(status_code=400, detail="验证码错误次数过多，请重新获取")
    if row.code != submitted:
        row.fail_count = int(row.fail_count or 0) + 1
        db.commit()
        raise HTTPException(status_code=400, detail="验证码不正确")
    row.used = 1
    db.commit()


def assert_phone_free(db: Session, phone: str, except_user_id: int | None = None) -> str:
    phone = normalize_phone(phone)
    owner = db.query(User).filter(User.phone == phone).first()
    if owner is not None and (except_user_id is None or int(owner.id) != int(except_user_id)):
        raise HTTPException(status_code=400, detail="该手机号已绑定其他账号")
    return phone


def user_by_phone(db: Session, phone: str) -> User | None:
    return db.query(User).filter(User.phone == normalize_phone(phone)).first()


def notify_user(db: Session, user: User | None, scene: str, content: str) -> None:
    if user is None:
        return
    phone = (getattr(user, "phone", None) or "").strip()
    if not phone:
        return
    send_notice(db, phone, scene, content, user_id=user.id)


def notify_admins(db: Session, scene: str, content: str) -> int:
    admins = db.query(User).filter(User.is_admin == 1).all()
    sent = 0
    for admin in admins:
        phone = (getattr(admin, "phone", None) or "").strip()
        if not phone:
            continue
        send_notice(db, phone, scene, content, user_id=admin.id)
        sent += 1
    if sent == 0:
        send_notice(db, "", scene, content, user_id=None)
    return sent


def notify_vip_opened(db: Session, user: User, package_name: str, days: int) -> None:
    notify_user(
        db,
        user,
        "vip_opened",
        f"会员开通提醒：{package_name} 已生效，有效期 {int(days)} 天。",
    )


def notify_admin_risk(db: Session, admin: User, action: str) -> None:
    who = admin.username or str(admin.id)
    notify_admins(db, "admin_risk", f"高危操作提醒：管理员 {who} 执行了「{action}」。")


def note_remote_login(db: Session, user: User, ip: str | None) -> None:
    current = (ip or "").strip()
    previous = (getattr(user, "last_login_ip", None) or "").strip()
    if previous and current and previous != current:
        notify_user(
            db,
            user,
            "remote_login",
            f"异地登录告警：你的账号刚从新地址 {current} 登录（上次 {previous}）。如非本人操作，请尽快修改密码。",
        )
    user.last_login_ip = current[:64]
    db.commit()


def alert_login_attack(db: Session, ip: str | None) -> None:
    global _last_attack_alert
    now = _now()
    if _last_attack_alert and now - _last_attack_alert < timedelta(minutes=10):
        return
    _last_attack_alert = now
    notify_admins(
        db,
        "system_alert",
        f"【系统告警】检测到来自 {ip or '未知地址'} 的高频登录攻击，请尽快查看后台日志。",
    )


def mfa_active(user: User) -> bool:
    until = getattr(user, "admin_mfa_until", None)
    return until is not None and until > _now()


def grant_admin_mfa(db: Session, user: User) -> datetime:
    until = _now() + MFA_TTL
    user.admin_mfa_until = until
    db.commit()
    return until
