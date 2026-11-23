"""日额度：免费用户限量，VIP 高额度/不限，促转化留存。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from database import UsageDaily, User
from vip_service import is_vip_active

# 免费档：能试用，用完引导开通 VIP
FREE_LIMITS = {
    "chat": 20,
    "image": 3,
}

# VIP：对话/生图基本不限（用大数）；视频/PPT 仍走 VIP 权益开关
VIP_LIMITS = {
    "chat": 9999,
    "image": 200,
}

FEATURE_LABELS = {
    "chat": "今日 AI 对话",
    "image": "今日 AI 生图",
}


class QuotaExceededError(Exception):
    def __init__(self, feature: str, used: int, limit: int):
        self.feature = feature
        self.used = used
        self.limit = limit
        label = FEATURE_LABELS.get(feature, feature)
        super().__init__(
            f"{label}已达今日上限（{used}/{limit}）。"
            "开通 VIP 可获得更高额度，并解锁视频生成与 PPT 下载。"
            "请到个人主页选择套餐充值。"
        )


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _limits_for(user: User) -> dict:
    return VIP_LIMITS if is_vip_active(user) else FREE_LIMITS


def _get_or_create_row(db: Session, user_id: int) -> UsageDaily:
    day = _today()
    row = (
        db.query(UsageDaily)
        .filter(UsageDaily.user_id == user_id, UsageDaily.day == day)
        .first()
    )
    if row is None:
        row = UsageDaily(user_id=user_id, day=day, chat_count=0, image_count=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def usage_counts(db: Session, user_id: int) -> dict:
    row = (
        db.query(UsageDaily)
        .filter(UsageDaily.user_id == user_id, UsageDaily.day == _today())
        .first()
    )
    return {
        "chat": int(row.chat_count) if row else 0,
        "image": int(row.image_count) if row else 0,
    }


def require_and_consume(db: Session, user: User, feature: str) -> None:
    """校验额度并 +1；不足则抛 QuotaExceededError。"""
    if feature not in ("chat", "image"):
        return
    limits = _limits_for(user)
    limit = int(limits.get(feature) or 0)
    row = _get_or_create_row(db, user.id)
    used = int(row.chat_count if feature == "chat" else row.image_count)
    if used >= limit:
        raise QuotaExceededError(feature, used, limit)
    if feature == "chat":
        row.chat_count = used + 1
    else:
        row.image_count = used + 1
    db.commit()


def usage_summary(db: Session, user: User) -> dict:
    limits = _limits_for(user)
    used = usage_counts(db, user.id)
    vip = is_vip_active(user)

    def item(feature: str) -> dict:
        lim = int(limits[feature])
        u = int(used.get(feature, 0))
        return {
            "feature": feature,
            "label": FEATURE_LABELS[feature],
            "used": u,
            "limit": lim,
            "remain": max(0, lim - u),
            "unlimited": vip and lim >= 9999,
        }

    return {
        "day": _today(),
        "is_vip": vip,
        "chat": item("chat"),
        "image": item("image"),
        "benefits": {
            "free": [
                f"每日 {FREE_LIMITS['chat']} 次 AI 对话",
                f"每日 {FREE_LIMITS['image']} 次 AI 生图",
                "视频生成、PPT 下载需开通 VIP",
            ],
            "vip": [
                "海量对话与生图额度",
                "解锁 AI 视频生成",
                "解锁 PPT 可下载文稿",
                "优先体验持续更新能力",
            ],
        },
    }
