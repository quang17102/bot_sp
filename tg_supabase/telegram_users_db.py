# -*- coding: utf-8 -*-
"""Lưu / cập nhật người dùng Telegram vào Supabase (bảng telegram_users)."""
import logging
from typing import Optional, Dict

from supabase import Client, create_client

from .supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


def save_user_on_start(telegram_user_id: int, full_name: str) -> None:
    """
    /start: chỉ insert khi user chưa có trong DB (free_voucher_turns=5, topup_turns=0).
    User cũ: không đọc/ghi DB. Cột first_name lưu full name khi tạo mới.
    """
    try:
        sb = _get_client()
        existing = (
            sb.table("telegram_users")
            .select("telegram_user_id")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return
        sb.table("telegram_users").insert(
            {
                "telegram_user_id": telegram_user_id,
                "first_name": full_name,
                # "free_voucher_turns": 5,
                # "topup_turns": 0,
            }
        ).execute()
    except Exception:
        logger.exception(
            "Không lưu được telegram_users cho user_id=%s",
            telegram_user_id,
        )


def get_telegram_user(telegram_user_id: int) -> Optional[Dict]:
    """Lấy một dòng từ bảng telegram_users theo telegram_user_id."""
    try:
        sb = _get_client()
        resp = (
            sb.table("telegram_users")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception:
        logger.exception(
            "Không lấy được telegram_users cho user_id=%s",
            telegram_user_id,
        )
        return None


def set_user_excel_link(telegram_user_id: int, excel_url: str) -> bool:
    """
    Ghi link Google Sheet (hoặc chuỗi tùy ý) vào cột excel.
    User chưa có dòng: insert tối thiểu telegram_user_id + excel.
    """
    excel_url = excel_url.strip()
    if not excel_url:
        return False
    try:
        sb = _get_client()
        existing = (
            sb.table("telegram_users")
            .select("telegram_user_id")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            sb.table("telegram_users").update({"excel": excel_url}).eq(
                "telegram_user_id", telegram_user_id
            ).execute()
        else:
            sb.table("telegram_users").insert(
                {"telegram_user_id": telegram_user_id, "excel": excel_url}
            ).execute()
        return True
    except Exception:
        logger.exception(
            "Không cập nhật được excel cho user_id=%s",
            telegram_user_id,
        )
        return False


def decrease_user_tien(telegram_user_id: int, amount: int) -> bool:
    """Trừ cột tien (đồng). Chỉ gọi khi đã kiểm tra đủ số dư."""
    if amount <= 0:
        return True
    try:
        sb = _get_client()
        row = get_telegram_user(telegram_user_id)
        if not row:
            return False
        cur = int(row.get("tien") or 0)
        new_val = cur - amount
        sb.table("telegram_users").update({"tien": new_val}).eq(
            "telegram_user_id", telegram_user_id
        ).execute()
        return True
    except Exception:
        logger.exception(
            "Không trừ được tien user_id=%s amount=%s",
            telegram_user_id,
            amount,
        )
        return False


def increase_user_tien(telegram_user_id: int, amount: int) -> bool:
    """Cộng cột tien (đồng), dùng khi nạp tiền custom thành công."""
    if amount <= 0:
        return True
    try:
        sb = _get_client()
        row = get_telegram_user(telegram_user_id)
        if not row:
            return False
        cur = int(row.get("tien") or 0)
        new_val = cur + amount
        sb.table("telegram_users").update({"tien": new_val}).eq(
            "telegram_user_id", telegram_user_id
        ).execute()
        return True
    except Exception:
        logger.exception(
            "Không cộng được tien user_id=%s amount=%s",
            telegram_user_id,
            amount,
        )
        return False
