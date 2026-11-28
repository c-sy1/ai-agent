"""VIP 权益、真实充值下单、支付成功后开通、后台开通。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import RechargeOrder, User
from payment_service import PaymentConfigError, build_page_pay_url, new_out_trade_no
from wechat_pay_service import WechatPaymentConfigError, build_native_code_url

# 正式环境默认隐藏 1 分钱测试套餐；本地调试可设 SHOW_VIP_TEST=1
SHOW_VIP_TEST = (os.getenv("SHOW_VIP_TEST") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

VIP_FEATURE_VIDEO = "video"
VIP_FEATURE_PPT = "pptx"

VIP_FEATURE_LABELS = {
    VIP_FEATURE_VIDEO: "AI 视频生成",
    VIP_FEATURE_PPT: "PPT 狂飙（可下载文稿）",
}

VIP_PACKAGES = [
    {
        "id": "vip_test",
        "name": "支付测试（1分钱）",
        "days": 1,
        "price": 0.01,
        "desc": "支付宝最低金额测到账；付成功开 1 天 VIP（无法收 0.0001）",
    },
    {
        "id": "vip_month",
        "name": "月度 VIP",
        "days": 30,
        "price": 9.9,
        "desc": "高额度对话/生图 + 视频 + PPT，30天",
    },
    {
        "id": "vip_quarter",
        "name": "季度 VIP",
        "days": 90,
        "price": 25.0,
        "desc": "高额度对话/生图 + 视频 + PPT，90天 · 更省",
    },
    {
        "id": "vip_year",
        "name": "年度 VIP",
        "days": 365,
        "price": 88.0,
        "desc": "全年畅用 · 视频 + PPT + 高额度，最划算",
    },
]


class VipRequiredError(Exception):
    def __init__(self, feature: str):
        self.feature = feature
        label = VIP_FEATURE_LABELS.get(feature, feature)
        super().__init__(
            f"{label} 为 VIP 专属。请到个人主页充值开通，或请管理员后台开通。"
        )


def _now() -> datetime:
    return datetime.utcnow()


def is_vip_active(user: User) -> bool:
    if not user or int(getattr(user, "is_vip", 0) or 0) != 1:
        return False
    expire = getattr(user, "vip_expire_at", None)
    if expire is None:
        return True
    return expire > _now()


def vip_status(user: User) -> dict:
    active = is_vip_active(user)
    expire = getattr(user, "vip_expire_at", None)
    return {
        "is_vip": active,
        "is_admin": bool(int(getattr(user, "is_admin", 0) or 0)),
        "vip_expire_at": expire.isoformat() if expire else None,
        "balance": float(getattr(user, "balance", 0) or 0),
        "vip_features": list(VIP_FEATURE_LABELS.values()) if active else [],
    }


def require_vip(user: User, feature: str) -> None:
    if not is_vip_active(user):
        raise VipRequiredError(feature)


def extend_vip(user: User, days: int) -> None:
    days = max(1, int(days))
    now = _now()
    base = user.vip_expire_at if (user.vip_expire_at and user.vip_expire_at > now) else now
    user.is_vip = 1
    user.vip_expire_at = base + timedelta(days=days)


def revoke_vip(user: User) -> None:
    user.is_vip = 0
    user.vip_expire_at = _now()


def get_package(package_id: str) -> dict | None:
    for p in VIP_PACKAGES:
        if p["id"] == package_id:
            return p
    return None


def list_public_packages() -> list[dict]:
    """用户端可见套餐（正式环境隐藏测试套餐）。"""
    out = []
    for p in VIP_PACKAGES:
        if p["id"] == "vip_test" and not SHOW_VIP_TEST:
            continue
        item = dict(p)
        item["recommended"] = p["id"] == "vip_quarter"
        out.append(item)
    return out


def create_vip_order(
    db: Session,
    user: User,
    package_id: str,
    *,
    channel: str = "alipay",
    coupon_code: str = "",
) -> tuple[RechargeOrder, dict]:
    """创建待支付订单并返回支付参数。channel: alipay | wechat。"""
    from coupon_service import apply_user_coupon, release_coupon, reserve_coupon

    pkg = get_package(package_id)
    if not pkg:
        raise ValueError("套餐不存在")
    if pkg["id"] == "vip_test" and not SHOW_VIP_TEST:
        raise ValueError("测试套餐已下线")

    channel = (channel or "alipay").strip().lower()
    if channel not in ("alipay", "wechat"):
        raise ValueError("支付方式仅支持 alipay 或 wechat")

    amount, coupon, coupon_row = apply_user_coupon(db, user, pkg["price"], coupon_code)
    remark = "待支付"
    if coupon:
        remark = f"待支付 · 券 {coupon['code']} 减 {coupon['off']}"

    out_trade_no = new_out_trade_no(user.id)
    order = RechargeOrder(
        user_id=user.id,
        package_id=pkg["id"],
        package_name=pkg["name"],
        amount=amount,
        days=pkg["days"],
        status="pending",
        channel=channel,
        remark=remark,
        out_trade_no=out_trade_no,
    )
    db.add(order)
    db.flush()

    subject = f"Apex AI {pkg['name']}"
    try:
        if channel == "wechat":
            code_url = build_native_code_url(
                out_trade_no=out_trade_no,
                description=subject,
                total_amount=amount,
            )
            pay = {"channel": "wechat", "code_url": code_url, "pay_url": ""}
        else:
            pay_url = build_page_pay_url(
                out_trade_no=out_trade_no,
                subject=subject,
                total_amount=amount,
            )
            pay = {"channel": "alipay", "pay_url": pay_url, "code_url": ""}
    except (PaymentConfigError, WechatPaymentConfigError):
        if coupon_row is not None:
            release_coupon(db, coupon_row)
        order.status = "closed"
        order.remark = "支付未配置"
        db.commit()
        raise

    if coupon_row is not None:
        reserve_coupon(db, coupon_row, order.id)
    db.commit()
    db.refresh(order)

    pay["amount"] = amount
    pay["original_amount"] = pkg["price"]
    pay["coupon"] = coupon
    return order, pay


def rebuild_pay_payload(order: RechargeOrder) -> dict:
    """待支付订单重新生成支付参数。"""
    subject = f"Apex AI {order.package_name}"
    channel = (order.channel or "alipay").strip().lower()
    if channel == "wechat":
        code_url = build_native_code_url(
            out_trade_no=order.out_trade_no,
            description=subject,
            total_amount=order.amount,
        )
        return {"channel": "wechat", "code_url": code_url, "pay_url": ""}
    pay_url = build_page_pay_url(
        out_trade_no=order.out_trade_no,
        subject=subject,
        total_amount=order.amount,
    )
    return {"channel": "alipay", "pay_url": pay_url, "code_url": ""}


def mark_order_paid(
    db: Session,
    out_trade_no: str,
    *,
    trade_no: str = "",
    channel: str = "",
) -> RechargeOrder | None:
    """支付成功回调：幂等开通 VIP。"""
    order = (
        db.query(RechargeOrder)
        .filter(RechargeOrder.out_trade_no == out_trade_no)
        .first()
    )
    if order is None:
        return None
    if order.status == "paid":
        return order

    user = db.get(User, order.user_id)
    if user is None:
        return order

    ch = (channel or order.channel or "alipay").strip().lower() or "alipay"
    label = "微信" if ch == "wechat" else "支付宝"
    extend_vip(user, order.days)
    order.status = "paid"
    order.remark = f"{label}已支付 {trade_no}".strip()
    order.channel = ch
    from coupon_service import mark_coupon_used_for_order

    mark_coupon_used_for_order(db, order.user_id, order.id)
    db.commit()
    db.refresh(order)
    from sms_service import notify_vip_opened

    notify_vip_opened(db, user, order.package_name, order.days)
    return order
