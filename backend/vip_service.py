"""VIP 权益、真实充值下单、支付成功后开通、后台开通。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import RechargeOrder, User
from payment_service import PaymentConfigError, build_page_pay_url, new_out_trade_no
from wechat_pay_service import WechatPaymentConfigError, build_native_code_url

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


def create_vip_order(
    db: Session,
    user: User,
    package_id: str,
    *,
    channel: str = "alipay",
) -> tuple[RechargeOrder, dict]:
    """创建待支付订单并返回支付参数。channel: alipay | wechat。"""
    pkg = get_package(package_id)
    if not pkg:
        raise ValueError("套餐不存在")

    channel = (channel or "alipay").strip().lower()
    if channel not in ("alipay", "wechat"):
        raise ValueError("支付方式仅支持 alipay 或 wechat")

    out_trade_no = new_out_trade_no(user.id)
    order = RechargeOrder(
        user_id=user.id,
        package_id=pkg["id"],
        package_name=pkg["name"],
        amount=pkg["price"],
        days=pkg["days"],
        status="pending",
        channel=channel,
        remark="待支付",
        out_trade_no=out_trade_no,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    subject = f"Apex AI {pkg['name']}"
    try:
        if channel == "wechat":
            code_url = build_native_code_url(
                out_trade_no=out_trade_no,
                description=subject,
                total_amount=pkg["price"],
            )
            pay = {"channel": "wechat", "code_url": code_url, "pay_url": ""}
        else:
            pay_url = build_page_pay_url(
                out_trade_no=out_trade_no,
                subject=subject,
                total_amount=pkg["price"],
            )
            pay = {"channel": "alipay", "pay_url": pay_url, "code_url": ""}
    except (PaymentConfigError, WechatPaymentConfigError):
        order.status = "closed"
        order.remark = "支付未配置"
        db.commit()
        raise

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
    db.commit()
    db.refresh(order)
    from sms_service import notify_vip_opened

    notify_vip_opened(db, user, order.package_name, order.days)
    return order
