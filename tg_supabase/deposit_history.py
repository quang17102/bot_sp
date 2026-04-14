# -*- coding: utf-8 -*-
"""Ghi lịch sử nạp tiền vào bảng deposit_history (Supabase)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from supabase import Client, create_client

from .supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


def log_deposit_history(
    *,
    telegram_user_id: int,
    chat_id: int,
    package_code: str,
    amount: int,
    payment_code: str,
    status: str,
    detail: str = "",
    transaction_ref: str = "",
    transaction_raw: Optional[dict[str, Any]] = None,
) -> bool:
    """Ghi một event lịch sử nạp tiền.

    status gợi ý: created | success | cancelled | expired | failed
    """
    try:
        payload: dict[str, Any] = {
            "telegram_user_id": int(telegram_user_id),
            "chat_id": int(chat_id),
            "package_code": (package_code or "").strip().lower(),
            "amount": int(amount or 0),
            "payment_code": (payment_code or "").strip(),
            "status": (status or "").strip().lower(),
            "detail": (detail or "").strip(),
            "transaction_ref": (transaction_ref or "").strip(),
        }
        if transaction_raw is not None:
            payload["transaction_raw"] = transaction_raw
        _get_client().table("deposit_history").insert(payload).execute()
        return True
    except Exception:
        logger.exception(
            "Không log được deposit_history user=%s payment_code=%s status=%s",
            telegram_user_id,
            payment_code,
            status,
        )
        return False
