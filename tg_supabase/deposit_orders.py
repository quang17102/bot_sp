# -*- coding: utf-8 -*-
"""Tạo đơn nạp tiền (deposit_orders) + tra giá gói (packages)."""
from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client, create_client

from .supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL

logger = logging.getLogger(__name__)

_client: Optional[Client] = None
TZ_VN = timezone(timedelta(hours=7))


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


def _now_vn() -> datetime:
    return datetime.now(TZ_VN)


def _gen_payment_code() -> str:
    # Chỉ chữ/số để phù hợp addInfo của VietQR.
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(13))


def get_package_price_k(package_code: str) -> Optional[int]:
    """Lấy giá gói từ bảng packages (đơn vị K nếu bạn lưu dạng 10,100,500...)."""
    code = (package_code or "").strip().lower()
    if not code:
        return None
    try:
        sb = _get_client()
        resp = (
            sb.table("packages")
            .select("code,price")
            .eq("code", code)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        price_raw = rows[0].get("price")
        if price_raw is None:
            return None
        price_k = int(price_raw)
        return price_k if price_k > 0 else None
    except Exception:
        logger.exception("Không lấy được packages.price cho code=%s", code)
        return None


def create_deposit_order(
    telegram_user_id: int,
    package_code: str,
    amount: int,
    *,
    expires_in_minutes: int = 15,
) -> dict:
    """Tạo 1 dòng deposit_orders tối giản theo schema hiện tại."""
    if amount <= 0:
        raise ValueError("amount phải > 0")
    code = (package_code or "").strip().lower()
    if not code:
        raise ValueError("package_code không được rỗng")

    now = _now_vn()
    expires_at = now + timedelta(minutes=expires_in_minutes)
    payment_code = _gen_payment_code()

    payload = {
        "telegram_user_id": telegram_user_id,
        "package_code": code,
        "amount": int(amount),
        "payment_code": payment_code,
        "expires_at": expires_at.isoformat(),
        "created_at": now.isoformat(),
    }

    sb = _get_client()
    resp = sb.table("deposit_orders").insert(payload).execute()
    rows = resp.data or []
    if not rows:
        raise RuntimeError("Không tạo được deposit_order")
    return rows[0]


def get_active_deposit_orders(limit: int = 200) -> list[dict]:
    """Lấy các lệnh nạp còn hạn để đối soát giao dịch."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        sb = _get_client()
        resp = (
            sb.table("deposit_orders")
            .select("*")
            .gt("expires_at", now_iso)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception:
        logger.exception("Không lấy được danh sách deposit_orders còn hạn")
        return []


def delete_deposit_order(order_id: int) -> bool:
    """Xóa lệnh nạp đã xử lý (hoặc bị hủy)."""
    try:
        sb = _get_client()
        sb.table("deposit_orders").delete().eq("id", int(order_id)).execute()
        return True
    except Exception:
        logger.exception("Không xóa được deposit_order id=%s", order_id)
        return False


def delete_deposit_order_by_payment_code(payment_code: str) -> bool:
    """Xóa lệnh nạp theo payment_code (dùng khi user hủy nạp)."""
    code = (payment_code or "").strip()
    if not code:
        return False
    try:
        sb = _get_client()
        sb.table("deposit_orders").delete().eq("payment_code", code).execute()
        return True
    except Exception:
        logger.exception("Không xóa được deposit_order payment_code=%s", code)
        return False


def get_deposit_order_by_payment_code(payment_code: str) -> Optional[dict]:
    """Lấy một order theo payment_code (nếu còn tồn tại)."""
    code = (payment_code or "").strip()
    if not code:
        return None
    try:
        sb = _get_client()
        resp = (
            sb.table("deposit_orders")
            .select("*")
            .eq("payment_code", code)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception:
        logger.exception("Không lấy được deposit_order payment_code=%s", code)
        return None
