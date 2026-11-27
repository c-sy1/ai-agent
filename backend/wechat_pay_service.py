"""微信支付 Native 扫码（真实收款）。需在 .env 配置商户参数。"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

_ENV = Path(__file__).resolve().parent / ".env"
_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_ENV, override=True)

WECHAT_NATIVE_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/native"


class WechatPaymentConfigError(Exception):
    pass


def _reload() -> None:
    load_dotenv(_ENV, override=True)


def _resolve_key_path(path: str) -> Path | None:
    p = Path(path)
    if not p.is_absolute():
        p = _BACKEND_DIR / p
    return p if p.is_file() else None


def _read_file_or_env(raw: str, path_env: str) -> str:
    path = (os.getenv(path_env) or "").strip()
    if path:
        resolved = _resolve_key_path(path)
        if resolved is not None:
            return resolved.read_text(encoding="utf-8-sig").strip()
    return (raw or "").strip().replace("\\n", "\n").strip().lstrip("\ufeff")


def _public_base() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def wechat_configured() -> bool:
    _reload()
    mch = (os.getenv("WECHAT_MCH_ID") or "").strip()
    app = (os.getenv("WECHAT_APP_ID") or "").strip()
    serial = (os.getenv("WECHAT_SERIAL_NO") or "").strip()
    api_v3 = (os.getenv("WECHAT_API_V3_KEY") or "").strip()
    priv = _read_file_or_env(os.getenv("WECHAT_PRIVATE_KEY", ""), "WECHAT_PRIVATE_KEY_PATH")
    return bool(
        mch
        and app
        and serial
        and len(api_v3) == 32
        and priv
        and "BEGIN" in priv.upper()
    )


def _load_private_key(pem: str):
    return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)


def _sign_message(message: str, private_key_pem: str) -> str:
    key = _load_private_key(private_key_pem)
    sig = key.sign(message.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def _authorization(method: str, canonical_url: str, body: str) -> str:
    mchid = os.getenv("WECHAT_MCH_ID", "").strip()
    serial = os.getenv("WECHAT_SERIAL_NO", "").strip()
    priv = _read_file_or_env(os.getenv("WECHAT_PRIVATE_KEY", ""), "WECHAT_PRIVATE_KEY_PATH")
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    message = f"{method}\n{canonical_url}\n{timestamp}\n{nonce}\n{body}\n"
    signature = _sign_message(message, priv)
    return (
        "WECHATPAY2-SHA256-RSA2048 "
        f'mchid="{mchid}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{serial}"'
    )


def build_native_code_url(
    *,
    out_trade_no: str,
    description: str,
    total_amount: float,
) -> str:
    """创建微信 Native 订单，返回 code_url（用于生成收款二维码）。"""
    _reload()
    if not wechat_configured():
        raise WechatPaymentConfigError(
            "未配置微信支付。请在 backend/.env 填写 WECHAT_MCH_ID、WECHAT_APP_ID、"
            "WECHAT_SERIAL_NO、WECHAT_API_V3_KEY、WECHAT_PRIVATE_KEY_PATH，"
            "并设置 PUBLIC_BASE_URL。"
        )

    total_fen = int(round(float(total_amount) * 100))
    if total_fen < 1:
        raise WechatPaymentConfigError("微信支付金额至少 0.01 元")

    notify_url = (
        os.getenv("WECHAT_NOTIFY_URL") or f"{_public_base()}/api/pay/wechat/notify"
    ).strip()
    body_obj = {
        "appid": os.getenv("WECHAT_APP_ID", "").strip(),
        "mchid": os.getenv("WECHAT_MCH_ID", "").strip(),
        "description": (description or "Apex AI VIP")[:127],
        "out_trade_no": out_trade_no,
        "notify_url": notify_url,
        "amount": {"total": total_fen, "currency": "CNY"},
    }
    body = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
    path = "/v3/pay/transactions/native"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": _authorization("POST", path, body),
    }
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(WECHAT_NATIVE_URL, headers=headers, content=body.encode("utf-8"))
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise WechatPaymentConfigError(f"微信下单失败：{detail}")
        data = resp.json()
    code_url = (data.get("code_url") or "").strip()
    if not code_url:
        raise WechatPaymentConfigError("微信未返回 code_url")
    return code_url


def decrypt_notify_resource(resource: dict) -> dict:
    """解密微信支付回调 resource。"""
    _reload()
    api_v3 = (os.getenv("WECHAT_API_V3_KEY") or "").strip().encode("utf-8")
    nonce = (resource.get("nonce") or "").encode("utf-8")
    associated = (resource.get("associated_data") or "").encode("utf-8")
    ciphertext_b64 = resource.get("ciphertext") or ""
    raw = base64.b64decode(ciphertext_b64)
    if len(raw) < 16:
        raise ValueError("ciphertext 无效")
    data, tag = raw[:-16], raw[-16:]
    aesgcm = AESGCM(api_v3)
    plain = aesgcm.decrypt(nonce, data + tag, associated)
    return json.loads(plain.decode("utf-8"))
