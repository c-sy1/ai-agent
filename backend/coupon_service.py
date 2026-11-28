"""用户优惠券：注册赠送、领取活动券、7 天有效、每人每券限用一次。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import User, UserCoupon

# 券模板：valid_days=领取后有效天数；once=每人只能持有/领取一次
COUPON_DEFS = {
    "APEX5": {
        "code": "APEX5",
        "label": "新人立减 ¥5",
        "off": 5.0,
        "min_amount": 9.9,
        "desc": "满 9.9 元可用，适合月度套餐",
        "valid_days": 7,
        "source": "welcome",
        "claimable": False,  # 仅注册自动发放
    },
    "APEX10": {
        "code": "APEX10",
        "label": "满减优惠 ¥10",
        "off": 10.0,
        "min_amount": 25.0,
        "desc": "满 25 元可用，适合季度/年度套餐",
        "valid_days": 7,
        "source": "campaign",
        "claimable": True,  # 活动页可领取一次
    },
}

WELCOME_CODE = "APEX5"


def _now() -> datetime:
    return datetime.utcnow()


def get_coupon_def(code: str) -> dict | None:
    c = (code or "").strip().upper()
    d = COUPON_DEFS.get(c)
    return dict(d) if d else None


def list_campaign_coupons() -> list[dict]:
    """可展示的活动券（含领取规则说明）。"""
    out = []
    for d in COUPON_DEFS.values():
        item = dict(d)
        item["how_to_get"] = (
            "注册自动到账"
            if d["code"] == WELCOME_CODE
            else ("点击领取，每人限领 1 张" if d.get("claimable") else "活动发放")
        )
        out.append(item)
    return out


def _coupon_status(row: UserCoupon) -> str:
    if row.used_at is not None:
        return "used"
    if row.expire_at and row.expire_at <= _now():
        return "expired"
    return "available"


def _row_dict(row: UserCoupon) -> dict:
    meta = get_coupon_def(row.coupon_code) or {
        "code": row.coupon_code,
        "label": row.coupon_code,
        "off": 0,
        "min_amount": 0,
        "desc": "",
        "valid_days": 7,
    }
    status = _coupon_status(row)
    return {
        "id": row.id,
        "code": row.coupon_code,
        "label": meta.get("label") or row.coupon_code,
        "off": float(meta.get("off") or 0),
        "min_amount": float(meta.get("min_amount") or 0),
        "desc": meta.get("desc") or "",
        "source": row.source or meta.get("source") or "",
        "status": status,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else "",
        "expire_at": row.expire_at.isoformat() if row.expire_at else "",
        "used_at": row.used_at.isoformat() if row.used_at else "",
        "order_id": row.order_id,
    }


def grant_coupon(
    db: Session,
    user: User,
    code: str,
    *,
    source: str = "",
    commit: bool = False,
) -> UserCoupon | None:
    """给用户发一张券；同码已有记录则不重复发。"""
    meta = get_coupon_def(code)
    if not meta:
        return None
    exists = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.coupon_code == meta["code"])
        .first()
    )
    if exists:
        return exists
    days = max(1, int(meta.get("valid_days") or 7))
    now = _now()
    row = UserCoupon(
        user_id=user.id,
        coupon_code=meta["code"],
        source=(source or meta.get("source") or "grant")[:40],
        claimed_at=now,
        expire_at=now + timedelta(days=days),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def grant_welcome_coupon(db: Session, user: User, *, commit: bool = False) -> UserCoupon | None:
    return grant_coupon(db, user, WELCOME_CODE, source="welcome", commit=commit)


def ensure_welcome_if_missing(db: Session, user: User) -> None:
    """老用户打开券包时补发一次新人券（若从未领过）。"""
    grant_welcome_coupon(db, user, commit=True)


def claim_coupon(db: Session, user: User, code: str) -> UserCoupon:
    meta = get_coupon_def(code)
    if not meta:
        raise ValueError("优惠券不存在")
    if not meta.get("claimable"):
        raise ValueError("该券不可手动领取（注册自动发放）")
    exists = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.coupon_code == meta["code"])
        .first()
    )
    if exists:
        raise ValueError("你已领取过该优惠券，每人限领 1 张")
    row = grant_coupon(db, user, meta["code"], source="claim", commit=True)
    if row is None:
        raise ValueError("领取失败")
    return row


def list_user_coupons(db: Session, user: User) -> list[dict]:
    ensure_welcome_if_missing(db, user)
    rows = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id)
        .order_by(UserCoupon.id.desc())
        .all()
    )
    return [_row_dict(r) for r in rows]


def find_usable_coupon(db: Session, user: User, code: str) -> UserCoupon:
    meta = get_coupon_def(code)
    if not meta:
        raise ValueError("优惠券无效或不存在")
    row = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.coupon_code == meta["code"])
        .first()
    )
    if row is None:
        raise ValueError("你还没有这张优惠券，请先领取或确认是否已注册到账")
    status = _coupon_status(row)
    if status == "used":
        raise ValueError("该优惠券已使用，每人限用 1 次")
    if status == "expired":
        raise ValueError("该优惠券已过期（领取后 7 天内有效）")
    return row


def apply_user_coupon(
    db: Session,
    user: User,
    amount: float,
    coupon_code: str = "",
) -> tuple[float, dict | None, UserCoupon | None]:
    code = (coupon_code or "").strip().upper()
    if not code:
        return float(amount), None, None
    row = find_usable_coupon(db, user, code)
    meta = get_coupon_def(code) or {}
    price = float(amount)
    if price < float(meta.get("min_amount") or 0):
        raise ValueError(f"未满足优惠券门槛（满 {meta.get('min_amount')} 元）")
    paid = max(0.01, round(price - float(meta.get("off") or 0), 2))
    return paid, meta, row


def mark_coupon_used(db: Session, row: UserCoupon, order_id: int) -> None:
    if row.used_at is not None:
        return
    row.used_at = _now()
    row.order_id = int(order_id)
