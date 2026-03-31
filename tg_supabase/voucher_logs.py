# -*- coding: utf-8 -*-
"""Quota lưu voucher theo ngày + gói unlimited (sv7, sv30) trên Supabase.

Yêu cầu bảng trong Supabase:

1) Bảng user_subscriptions (đã có):
   - telegram_user_id: bigint
   - package_code: text      -- 'sv7', 'sv30', ...
   - started_at: timestamptz
   - expires_at: timestamptz
   - status: text            -- 'active', ...

2) Bảng voucher_logs (dùng để đếm lượt free/ngày):

   CREATE TABLE voucher_logs (
     id               bigserial PRIMARY KEY,
     telegram_user_id bigint NOT NULL,
     created_at       timestamptz NOT NULL DEFAULT now(),
     is_free          boolean NOT NULL DEFAULT true,
     note             text
   );

- Mỗi lần lưu voucher xong, gọi log_voucher_save(...) để ghi log.
- Trước khi lưu, gọi can_save_voucher(...) để kiểm tra quota.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

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


def _today_vn() -> date:
    return datetime.now(TZ_VN).date()


def has_unlimited_voucher(telegram_user_id: int) -> bool:
    """Kiểm tra user có gói voucher unlimited (sv7/sv30) còn hạn hay không."""
    sb = _get_client()
    now = datetime.now(TZ_VN).isoformat()
    try:
        resp = (
            sb.table("user_subscriptions")
            .select("id")
            .eq("telegram_user_id", telegram_user_id)
            .in_("package_code", ["sv7", "sv30"])
            .eq("status", "active")
            .gt("expires_at", now)
            .limit(1)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        logger.exception(
            "Lỗi khi kiểm tra unlimited voucher cho user_id=%s", telegram_user_id
        )
        # Nếu lỗi, an toàn hơn là coi như KHÔNG có gói (tránh free unlimited).
        return False


def get_active_voucher_subscription(telegram_user_id: int) -> Optional[Dict[str, Any]]:
    """Gói voucher unlimited đang active (sv7/sv30): package_code + expires_at."""
    sb = _get_client()
    now = datetime.now(TZ_VN).isoformat()
    try:
        resp = (
            sb.table("user_subscriptions")
            .select("package_code,expires_at")
            .eq("telegram_user_id", telegram_user_id)
            .in_("package_code", ["sv7", "sv30"])
            .eq("status", "active")
            .gt("expires_at", now)
            .order("expires_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        return rows[0]
    except Exception:
        logger.exception(
            "Lỗi khi lấy voucher subscription cho user_id=%s", telegram_user_id
        )
        return None


def get_active_voucher_package_code(telegram_user_id: int) -> Optional[str]:
    """Lấy package_code voucher unlimited đang active (sv7/sv30), nếu có."""
    sub = get_active_voucher_subscription(telegram_user_id)
    if not sub:
        return None
    return (sub.get("package_code") or "").strip() or None


def get_free_voucher_used_today(telegram_user_id: int) -> int:
    """Đếm số lượt lưu voucher free trong ngày (theo VN)."""
    sb = _get_client()
    today = _today_vn().isoformat()  # 'YYYY-MM-DD'
    try:
        # created_at::date = today (Postgres)
        resp = (
            sb.table("voucher_logs")
            .select("id", count="exact")
            .eq("telegram_user_id", telegram_user_id)
            .eq("is_free", True)
            .gte("created_at", today)
            .lt("created_at", today + "T23:59:59.999999+07:00")
            .execute()
        )
        # supabase-py v2 trả count ở resp.count; nếu không có, fallback len(data)
        if getattr(resp, "count", None) is not None:
            return int(resp.count or 0)
        return len(resp.data or [])
    except Exception:
        logger.exception(
            "Lỗi khi đếm free voucher hôm nay cho user_id=%s", telegram_user_id
        )
        return 0


def can_save_voucher(telegram_user_id: int, daily_free_limit: int = 5) -> Tuple[bool, str]:
    """Kiểm tra user còn quyền lưu voucher không.

    Trả về (ok, reason):
    - ok=True  → được phép lưu.
    - ok=False → hết 5 lượt free và không có gói unlimited.
    """
    # Nếu có gói unlimited (sv7/sv30) thì cho lưu không giới hạn.
    if has_unlimited_voucher(telegram_user_id):
        return True, "unlimited"

    used = get_free_voucher_used_today(telegram_user_id)
    if used < daily_free_limit:
        return True, f"free_left_{daily_free_limit - used}"
    return False, "no_free_quota"


def log_voucher_save(
    telegram_user_id: int,
    is_free: bool = True,
    note: Optional[str] = None,
) -> None:
    """Ghi log một lần lưu voucher.

    - is_free=True  → lượt free (dùng cho quota).
    - is_free=False → lượt do gói unlimited / trả phí.
    """
    sb = _get_client()
    try:
        payload = {
            "telegram_user_id": telegram_user_id,
            "is_free": is_free,
        }
        if note:
            payload["note"] = note
        sb.table("voucher_logs").insert(payload).execute()
    except Exception:
        logger.exception(
            "Không log được voucher_logs cho user_id=%s (is_free=%s)",
            telegram_user_id,
            is_free,
        )

