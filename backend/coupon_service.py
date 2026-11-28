"""用户优惠券：注册赠送、领取活动券、客服赠券、7 天有效。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import User, UserCoupon

# 券模板：valid_days=领取后有效天数
COUPON_DEFS = {
    "APEX5": {
        "code": "APEX5",
        "label": "新人立减 ¥5",
        "off": 5.0,
        "min_amount": 9.9,
        "desc": "满 9.9 元可用，适合月度套餐",
        "valid_days": 7,
        "source": "welcome",
        "claimable": False,
        "admin_grant": False,
    },
    "APEX10": {
        "code": "APEX10",
        "label": "满减优惠 ¥10",
        "off": 10.0,
        "min_amount": 25.0,
        "desc": "满 25 元可用，适合季度/年度套餐",
        "valid_days": 7,
        "source": "campaign",
        "claimable": True,
        "admin_grant": False,
    },
    # 客服补偿券（不可自领，由管理员赠送；每次赠送生成唯一码）
    "COMP5": {
        "code": "COMP5",
        "label": "客服补偿 ¥5",
        "off": 5.0,
        "min_amount": 9.9,
        "desc": "客服补偿券，满 9.9 可用",
        "valid_days": 14,
        "source": "support",
        "claimable": False,
        "admin_grant": True,
    },
    "COMP10": {
        "code": "COMP10",
        "label": "客服补偿 ¥10",
        "off": 10.0,
        "min_amount": 9.9,
        "desc": "客服补偿券，满 9.9 可用",
        "valid_days": 14,
        "source": "support",
        "claimable": False,
        "admin_grant": True,
    },
    "COMP20": {
        "code": "COMP20",
        "label": "客服补偿 ¥20",
        "off": 20.0,
        "min_amount": 25.0,
        "desc": "客服补偿券，满 25 可用",
        "valid_days": 14,
        "source": "support",
        "claimable": False,
        "admin_grant": True,
    },
}

WELCOME_CODE = "APEX5"


def _now() -> datetime:
    return datetime.utcnow()


def get_coupon_def(code: str) -> dict | None:
    c = (code or "").strip().upper()
    if not c:
        return None
    if c in COUPON_DEFS:
        return dict(COUPON_DEFS[c])
    # 客服赠送唯一码：COMP10-T12 / COMP5-U3-2
    for base in ("COMP20", "COMP10", "COMP5", "APEX10", "APEX5"):
        if c == base or c.startswith(base + "-"):
            d = dict(COUPON_DEFS[base])
            d["code"] = c
            return d
    return None


def list_campaign_coupons() -> list[dict]:
    """用户可见活动券（不含仅后台赠送的补偿券）。"""
    out = []
    for d in COUPON_DEFS.values():
        if d.get("admin_grant") and not d.get("claimable") and d["source"] == "support":
            continue
        item = dict(d)
        item["how_to_get"] = (
            "注册自动到账"
            if d["code"] == WELCOME_CODE
            else ("点击领取，每人限领 1 张" if d.get("claimable") else "活动发放")
        )
        out.append(item)
    return out


def list_grantable_coupons() -> list[dict]:
    """管理端可赠送的券模板。"""
    return [dict(d) for d in COUPON_DEFS.values() if d.get("admin_grant")]


def _meta_for_row(row: UserCoupon) -> dict:
    meta = get_coupon_def(row.coupon_code) or {
        "code": row.coupon_code,
        "label": row.coupon_code,
        "off": 0,
        "min_amount": 0,
        "desc": "",
        "valid_days": 7,
        "source": row.source or "",
    }
    label = (getattr(row, "label", None) or "").strip()
    if label:
        meta["label"] = label
    if getattr(row, "off_amount", None) is not None:
        meta["off"] = float(row.off_amount)
    if getattr(row, "min_amount", None) is not None:
        meta["min_amount"] = float(row.min_amount)
    note = (getattr(row, "note", None) or "").strip()
    if note:
        meta["desc"] = note
    meta["code"] = row.coupon_code
    return meta


def _coupon_status(row: UserCoupon) -> str:
    if row.used_at is not None:
        return "used"
    if row.order_id is not None:
        return "reserved"
    if row.expire_at and row.expire_at <= _now():
        return "expired"
    return "available"


def _row_dict(row: UserCoupon) -> dict:
    meta = _meta_for_row(row)
    status = _coupon_status(row)
    return {
        "id": row.id,
        "code": row.coupon_code,
        "label": meta.get("label") or row.coupon_code,
        "off": float(meta.get("off") or 0),
        "min_amount": float(meta.get("min_amount") or 0),
        "desc": meta.get("desc") or "",
        "source": row.source or meta.get("source") or "",
        "note": getattr(row, "note", "") or "",
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
    """给用户发一张模板券；同码已有记录则不重复发。"""
    meta = get_coupon_def(code)
    if not meta:
        return None
    base_code = meta["code"] if meta["code"] in COUPON_DEFS else code.strip().upper()
    # 活动/新人券用固定码；补偿唯一码已在 meta.code
    store_code = base_code if base_code in COUPON_DEFS and not meta.get("admin_grant") else meta["code"]
    exists = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.coupon_code == store_code)
        .first()
    )
    if exists:
        return exists
    days = max(1, int(meta.get("valid_days") or 7))
    now = _now()
    row = UserCoupon(
        user_id=user.id,
        coupon_code=store_code,
        source=(source or meta.get("source") or "grant")[:40],
        label=(meta.get("label") or "")[:80],
        off_amount=float(meta.get("off") or 0),
        min_amount=float(meta.get("min_amount") or 0),
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
    grant_welcome_coupon(db, user, commit=True)


def claim_coupon(db: Session, user: User, code: str) -> UserCoupon:
    meta = get_coupon_def(code)
    if not meta:
        raise ValueError("优惠券不存在")
    if not meta.get("claimable"):
        raise ValueError("该券不可手动领取")
    fixed = meta["code"] if meta["code"] in COUPON_DEFS else code.strip().upper()
    if fixed not in COUPON_DEFS or not COUPON_DEFS[fixed].get("claimable"):
        raise ValueError("该券不可手动领取")
    exists = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.coupon_code == fixed)
        .first()
    )
    if exists:
        raise ValueError("你已领取过该优惠券，每人限领 1 张")
    row = grant_coupon(db, user, fixed, source="claim", commit=True)
    if row is None:
        raise ValueError("领取失败")
    return row


def grant_support_coupon(
    db: Session,
    user: User,
    template: str,
    *,
    ticket_id: int | None = None,
    note: str = "",
    off: float | None = None,
    min_amount: float | None = None,
    valid_days: int | None = None,
    commit: bool = True,
) -> UserCoupon:
    """客服赠券：每次生成唯一券码，可多次赠送。"""
    tpl = (template or "").strip().upper()
    meta = COUPON_DEFS.get(tpl)
    if meta is None or not meta.get("admin_grant"):
        raise ValueError("不支持的补偿券模板，请使用 COMP5 / COMP10 / COMP20")
    count = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.source == "support")
        .count()
    )
    if ticket_id:
        code = f"{tpl}-T{int(ticket_id)}"
    else:
        code = f"{tpl}-U{user.id}-{count + 1}"
    # 同码冲突则加后缀
    base = code
    n = 1
    while (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.coupon_code == code)
        .first()
    ):
        n += 1
        code = f"{base}-{n}"

    days = max(1, int(valid_days if valid_days is not None else meta.get("valid_days") or 14))
    now = _now()
    off_v = float(off if off is not None else meta["off"])
    min_v = float(min_amount if min_amount is not None else meta["min_amount"])
    row = UserCoupon(
        user_id=user.id,
        coupon_code=code,
        source="support",
        label=(meta.get("label") or f"客服补偿 ¥{off_v}")[:80],
        off_amount=off_v,
        min_amount=min_v,
        note=(note or meta.get("desc") or "")[:200],
        claimed_at=now,
        expire_at=now + timedelta(days=days),
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
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
    raw = (code or "").strip().upper()
    if not raw:
        raise ValueError("优惠券无效或不存在")
    row = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user.id, UserCoupon.coupon_code == raw)
        .first()
    )
    if row is None:
        raise ValueError("你还没有这张优惠券，请先领取或确认是否已注册到账")
    status = _coupon_status(row)
    if status == "used":
        raise ValueError("该优惠券已使用，每人限用 1 次")
    if status == "reserved":
        raise ValueError("该优惠券正在支付订单中占用，请先取消待支付订单或完成支付")
    if status == "expired":
        raise ValueError("该优惠券已过期")
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
    meta = _meta_for_row(row)
    price = float(amount)
    if price < float(meta.get("min_amount") or 0):
        raise ValueError(f"未满足优惠券门槛（满 {meta.get('min_amount')} 元）")
    paid = max(0.01, round(price - float(meta.get("off") or 0), 2))
    return paid, meta, row


def reserve_coupon(db: Session, row: UserCoupon, order_id: int) -> None:
    if row.used_at is not None:
        raise ValueError("该优惠券已使用，每人限用 1 次")
    if row.order_id is not None and int(row.order_id) != int(order_id):
        raise ValueError("该优惠券正在其他订单中占用")
    row.order_id = int(order_id)


def release_coupon(db: Session, row: UserCoupon) -> None:
    if row.used_at is not None:
        return
    row.order_id = None


def mark_coupon_used(db: Session, row: UserCoupon, order_id: int) -> None:
    row.order_id = int(order_id)
    if row.used_at is None:
        row.used_at = _now()


def mark_coupon_used_for_order(db: Session, user_id: int, order_id: int) -> None:
    row = (
        db.query(UserCoupon)
        .filter(UserCoupon.user_id == user_id, UserCoupon.order_id == order_id)
        .first()
    )
    if row is not None:
        mark_coupon_used(db, row, order_id)
