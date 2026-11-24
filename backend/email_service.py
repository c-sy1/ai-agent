"""邮箱验证码：个人 QQ/163 SMTP 即可真收，无需企业资质。"""
from __future__ import annotations

import os
import random
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import SmsLog, User

load_dotenv()

CODE_TTL = timedelta(minutes=5)
RESEND_GAP = timedelta(seconds=60)
MAX_FAILS = 5

EMAIL_SCENES = {
    "register": "注册",
    "email_login": "邮箱登录",
    "reset_password": "找回密码",
    "admin_mfa": "管理员二次验证",
    "pay_confirm": "支付确认",
}


def _reload() -> None:
    load_dotenv(override=True)


def email_configured() -> bool:
    _reload()
    return bool(
        (os.getenv("SMTP_HOST") or "").strip()
        and (os.getenv("SMTP_USER") or "").strip()
        and (os.getenv("SMTP_PASSWORD") or "").strip()
    )


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status_code=400, detail="请填写正确的邮箱地址")
    return value[:100]


def mask_email(email: str | None) -> str:
    e = (email or "").strip()
    if "@" not in e:
        return ""
    name, domain = e.split("@", 1)
    if len(name) <= 2:
        shown = name[:1] + "*"
    else:
        shown = name[:2] + "***"
    return f"{shown}@{domain}"


def _now() -> datetime:
    return datetime.utcnow()


def _target_key(email: str) -> str:
    # 复用 sms_logs.phone 字段存邮箱（已加宽），加前缀避免和手机号冲突
    return f"mail:{normalize_email(email)}"


def _latest(db: Session, email: str, scene: str) -> SmsLog | None:
    key = _target_key(email)
    return (
        db.query(SmsLog)
        .filter(SmsLog.phone == key, SmsLog.scene == scene, SmsLog.kind == "code")
        .order_by(SmsLog.id.desc())
        .first()
    )


def _smtp_send(to_email: str, subject: str, body: str) -> None:
    _reload()
    host = (os.getenv("SMTP_HOST") or "").strip()
    port = int(os.getenv("SMTP_PORT") or "465")
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    from_name = (os.getenv("SMTP_FROM_NAME") or "Apex AI").strip()
    use_ssl = (os.getenv("SMTP_SSL") or "true").strip().lower() in ("1", "true", "yes", "on")

    if not (host and user and password):
        raise HTTPException(
            status_code=503,
            detail="邮箱发信未配置。请在 .env 填写 SMTP_HOST / SMTP_USER / SMTP_PASSWORD（QQ邮箱用授权码）",
        )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = to_email

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                smtp.login(user, password)
                smtp.sendmail(user, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(user, password)
                smtp.sendmail(user, [to_email], msg.as_string())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"邮件发送失败：{e}") from e


def send_email_code(
    db: Session,
    email: str,
    scene: str,
    user_id: int | None = None,
) -> dict:
    if scene not in EMAIL_SCENES:
        raise HTTPException(status_code=400, detail="不支持的邮箱验证码场景")
    email = normalize_email(email)
    prev = _latest(db, email, scene)
    if prev and prev.created_at and _now() - prev.created_at < RESEND_GAP and int(prev.used or 0) == 0:
        raise HTTPException(status_code=429, detail="验证码已发送，请 60 秒后再试")

    code = f"{random.randint(0, 999999):06d}"
    label = EMAIL_SCENES[scene]
    content = f"【Apex AI】验证码 {code}，5 分钟内有效，用于{label}。请勿泄露。"
    row = SmsLog(
        phone=_target_key(email),
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

    demo = (os.getenv("EMAIL_DEMO") or "").strip().lower() in ("1", "true", "yes")
    if demo or not email_configured():
        return {
            "email": mask_email(email),
            "scene": scene,
            "channel": "email",
            "demo": True,
            "demo_code": code,
            "provider": "demo",
        }

    try:
        _smtp_send(
            email,
            f"Apex AI 验证码 - {label}",
            f"您的验证码是：{code}\n\n用于{label}，5 分钟内有效。如非本人操作请忽略。\n\n— Apex AI",
        )
    except HTTPException:
        row.used = 1
        db.commit()
        raise

    return {
        "email": mask_email(email),
        "scene": scene,
        "channel": "email",
        "demo": False,
        "provider": "smtp",
    }


def verify_email_code(db: Session, email: str, scene: str, code: str) -> None:
    email = normalize_email(email)
    submitted = (code or "").strip()
    if not re.fullmatch(r"\d{6}", submitted):
        raise HTTPException(status_code=400, detail="请输入 6 位邮箱验证码")
    row = _latest(db, email, scene)
    if row is None or int(row.used or 0) == 1:
        raise HTTPException(status_code=400, detail="请先获取邮箱验证码")
    if row.created_at and _now() - row.created_at > CODE_TTL:
        row.used = 1
        db.commit()
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    if int(row.fail_count or 0) >= MAX_FAILS:
        row.used = 1
        db.commit()
        raise HTTPException(status_code=400, detail="验证码错误次数过多，请重新获取")
    if row.code != submitted:
        row.fail_count = int(row.fail_count or 0) + 1
        db.commit()
        raise HTTPException(status_code=400, detail="验证码不正确")
    row.used = 1
    db.commit()


def user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == normalize_email(email)).first()
