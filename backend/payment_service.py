"""支付宝电脑网站支付（真实收款）。需在 .env 配置商户参数。"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlencode

from dotenv import load_dotenv

_ENV = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV, override=True)

GATEWAY_PROD = "https://openapi.alipay.com/gateway.do"
GATEWAY_SANDBOX = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"


class PaymentConfigError(Exception):
    pass


def _reload() -> None:
    load_dotenv(_ENV, override=True)


_BACKEND_DIR = Path(__file__).resolve().parent


def _resolve_key_path(path: str) -> Path | None:
    p = Path(path)
    if not p.is_absolute():
        p = _BACKEND_DIR / p
    return p if p.is_file() else None


def _read_key(raw: str, path_env: str) -> str:
    path = (os.getenv(path_env) or "").strip()
    if path:
        resolved = _resolve_key_path(path)
        if resolved is not None:
            text = resolved.read_text(encoding="utf-8-sig").strip()
            if "在这里粘贴" in text or "粘贴你的应用私钥" in text:
                return ""
            return text
    text = (raw or "").strip()
    if not text:
        return ""
    # 支持 .env 里用 \n 写成一行；去掉 UTF-8 BOM
    return text.replace("\\n", "\n").strip().lstrip("\ufeff")


def alipay_configured() -> bool:
    _reload()
    app_id = (os.getenv("ALIPAY_APP_ID") or "").strip()
    priv = _read_key(os.getenv("ALIPAY_PRIVATE_KEY", ""), "ALIPAY_PRIVATE_KEY_PATH")
    pub = _read_key(
        os.getenv("ALIPAY_ALIPAY_PUBLIC_KEY", "") or os.getenv("ALIPAY_PUBLIC_KEY", ""),
        "ALIPAY_PUBLIC_KEY_PATH",
    )
    priv = (priv or "").lstrip("\ufeff")
    pub = (pub or "").lstrip("\ufeff")
    # 应用私钥常见为 BEGIN PRIVATE KEY / BEGIN RSA PRIVATE KEY
    return bool(app_id and priv and pub and "BEGIN" in priv.upper())


def _gateway() -> str:
    sandbox = (os.getenv("ALIPAY_SANDBOX") or "true").strip().lower() in ("1", "true", "yes")
    return GATEWAY_SANDBOX if sandbox else GATEWAY_PROD


def _public_base() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def new_out_trade_no(user_id: int) -> str:
    return f"APX{user_id}{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8]}"


def _normalize_pem(key_data: str, *, kind: str) -> str:
    text = (key_data or "").strip().replace("\r", "")
    if "BEGIN" in text:
        return text
    if kind == "private":
        return (
            "-----BEGIN PRIVATE KEY-----\n"
            + text
            + "\n-----END PRIVATE KEY-----"
        )
    return (
        "-----BEGIN PUBLIC KEY-----\n" + text + "\n-----END PUBLIC KEY-----"
    )


def _load_private_key(private_key_pem: str):
    from cryptography.hazmat.primitives import serialization

    raw = private_key_pem.strip().replace("\r", "")
    candidates = []
    if "BEGIN" in raw:
        candidates.append(raw)
        # 有的工具把 PKCS8 标成 RSA PRIVATE KEY，或反过来
        if "RSA PRIVATE KEY" in raw:
            candidates.append(
                raw.replace("RSA PRIVATE KEY", "PRIVATE KEY")
            )
        elif "BEGIN PRIVATE KEY" in raw and "RSA" not in raw.split("\n")[0]:
            candidates.append(
                raw.replace("PRIVATE KEY", "RSA PRIVATE KEY")
            )
    else:
        candidates.append(_normalize_pem(raw, kind="private"))
        candidates.append(
            "-----BEGIN RSA PRIVATE KEY-----\n"
            + raw
            + "\n-----END RSA PRIVATE KEY-----"
        )

    last_err: Exception | None = None
    for item in candidates:
        try:
            return serialization.load_pem_private_key(
                item.encode("utf-8"), password=None
            )
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise ValueError(f"应用私钥无法解析，请确认 PEM 完整：{last_err}")


def _sign_rsa2(content: str, private_key_pem: str) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    private_key = _load_private_key(private_key_pem)
    signature = private_key.sign(
        content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")


def _verify_rsa2(content: str, sign: str, public_key_pem: str) -> bool:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.exceptions import InvalidSignature

    key_data = public_key_pem
    if "BEGIN" not in key_data:
        key_data = (
            "-----BEGIN PUBLIC KEY-----\n" + key_data + "\n-----END PUBLIC KEY-----"
        )
    public_key = serialization.load_pem_public_key(key_data.encode("utf-8"))
    try:
        public_key.verify(
            base64.b64decode(sign),
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False


def build_page_pay_url(
    *,
    out_trade_no: str,
    subject: str,
    total_amount: float,
) -> str:
    """生成支付宝电脑网站支付跳转 URL。未配置商户参数时抛错。"""
    _reload()
    if not alipay_configured():
        raise PaymentConfigError(
            "未配置支付宝收款参数。请在 backend/.env 填写 ALIPAY_APP_ID、"
            "ALIPAY_PRIVATE_KEY（或 PATH）、ALIPAY_ALIPAY_PUBLIC_KEY，"
            "并设置 PUBLIC_BASE_URL 为可被支付宝访问的域名。"
        )

    app_id = os.getenv("ALIPAY_APP_ID", "").strip()
    private_key = _read_key(os.getenv("ALIPAY_PRIVATE_KEY", ""), "ALIPAY_PRIVATE_KEY_PATH")
    notify_url = (os.getenv("ALIPAY_NOTIFY_URL") or f"{_public_base()}/api/pay/alipay/notify").strip()
    return_url = (os.getenv("ALIPAY_RETURN_URL") or f"{_public_base()}/api/pay/alipay/return").strip()

    biz = {
        "out_trade_no": out_trade_no,
        "product_code": "FAST_INSTANT_TRADE_PAY",
        "total_amount": f"{float(total_amount):.2f}",
        "subject": subject[:128],
    }
    params = {
        "app_id": app_id,
        "method": "alipay.trade.page.pay",
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0",
        "notify_url": notify_url,
        "return_url": return_url,
        "biz_content": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
    }
    unsigned = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
    params["sign"] = _sign_rsa2(unsigned, private_key)
    return f"{_gateway()}?{urlencode(params, quote_via=quote_plus)}"


def verify_alipay_callback(params: dict) -> bool:
    _reload()
    public_key = _read_key(
        os.getenv("ALIPAY_ALIPAY_PUBLIC_KEY", "") or os.getenv("ALIPAY_PUBLIC_KEY", ""),
        "ALIPAY_PUBLIC_KEY_PATH",
    )
    if not public_key:
        return False
    sign = params.get("sign")
    if not sign:
        return False
    data = {k: v for k, v in params.items() if k not in ("sign", "sign_type") and v is not None}
    unsigned = "&".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    return _verify_rsa2(unsigned, sign, public_key)
