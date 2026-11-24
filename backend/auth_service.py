"""账号安全：密码 bcrypt 哈希、JWT 签发校验、登录失败限流。"""
from __future__ import annotations

import os
import time
from datetime import datetime
from threading import Lock

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import User, get_db

load_dotenv()

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS") or "168")  # 默认 7 天
_LOGIN_WINDOW_SEC = 600
_LOGIN_MAX_FAILS = 8
_fail_lock = Lock()
_fail_map: dict[str, list[float]] = {}


def _jwt_secret() -> str:
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if secret:
        return secret
    # 开发兜底；生产务必在 .env 配置 JWT_SECRET
    return "apex-ai-dev-jwt-secret-change-me"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode(
        "ascii"
    )


def is_hashed_password(stored: str) -> bool:
    s = (stored or "").strip()
    return s.startswith("$2a$") or s.startswith("$2b$") or s.startswith("$2y$")


def verify_password(plain: str, stored: str) -> bool:
    if not plain or not stored:
        return False
    if is_hashed_password(stored):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("ascii"))
        except ValueError:
            return False
    # 兼容旧库明文，校验成功后由调用方升级哈希
    return plain == stored


def create_access_token(user: User) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_admin": bool(int(getattr(user, "is_admin", 0) or 0)),
        "iat": now,
        "exp": now + JWT_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="无效的登录凭证") from e


def _client_key(username: str, ip: str | None) -> str:
    return f"{(ip or 'unknown').strip()}|{(username or '').strip().lower()}"


def check_login_rate_limit(username: str, ip: str | None = None) -> None:
    key = _client_key(username, ip)
    now = time.time()
    with _fail_lock:
        stamps = [t for t in _fail_map.get(key, []) if now - t < _LOGIN_WINDOW_SEC]
        _fail_map[key] = stamps
        if len(stamps) >= _LOGIN_MAX_FAILS:
            raise HTTPException(
                status_code=429,
                detail="登录失败次数过多，请 10 分钟后再试",
            )


def record_login_failure(username: str, ip: str | None = None) -> None:
    key = _client_key(username, ip)
    now = time.time()
    with _fail_lock:
        stamps = [t for t in _fail_map.get(key, []) if now - t < _LOGIN_WINDOW_SEC]
        stamps.append(now)
        _fail_map[key] = stamps


def clear_login_failures(username: str, ip: str | None = None) -> None:
    key = _client_key(username, ip)
    with _fail_lock:
        _fail_map.pop(key, None)


def auth_payload_for(user: User) -> dict:
    from vip_service import vip_status

    return {
        "user_id": user.id,
        "username": user.username,
        "nickname": user.nickname or user.username,
        "email": user.email,
        "phone": (getattr(user, "phone", None) or ""),
        "access_token": create_access_token(user),
        "token_type": "Bearer",
        **vip_status(user),
    }


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_access_token(token)
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=401, detail="无效的登录凭证") from e
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被删除")
    if int(getattr(user, "is_disabled", 0) or 0) == 1:
        raise HTTPException(status_code=403, detail="账号已禁用，请联系管理员")
    return user


def assert_self_or_admin(auth: User, user_id: int) -> None:
    if int(auth.id) == int(user_id):
        return
    if int(getattr(auth, "is_admin", 0) or 0) == 1:
        return
    raise HTTPException(status_code=403, detail="无权操作该账号数据")


def require_admin(auth: User) -> None:
    if int(getattr(auth, "is_admin", 0) or 0) != 1:
        raise HTTPException(status_code=403, detail="需要管理员权限")


def require_admin_mfa(auth: User) -> None:
    """原为邮箱二次验证；课程演示改为仅校验管理员身份。"""
    require_admin(auth)
