# -*- coding: utf-8 -*-
"""Yêu cầu reg acc → bảng public.reg_acc (Supabase).

Insert: id_tele (text = str(telegram_user_id)), sl (bigint). Cột khác NULL/default.

Nếu đã có bất kỳ dòng nào cùng id_tele thì không cho thêm (user phải xóa/đổi dòng
trên DB sau khi xử lý xong mới /reg lại được).
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from supabase import Client, create_client

from .supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


def _id_tele(telegram_user_id: int) -> str:
    return str(telegram_user_id)


def has_reg_acc_row_for_user(telegram_user_id: int) -> bool:
    """True nếu đã tồn tại ít nhất một dòng reg_acc với id_tele = user (bất kể status)."""
    try:
        sb = _get_client()
        resp = (
            sb.table("reg_acc")
            .select("id")
            .eq("id_tele", _id_tele(telegram_user_id))
            .limit(1)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        logger.exception("Không kiểm tra được reg_acc cho user_id=%s", telegram_user_id)
        return True


RegInsertResult = Literal["ok", "busy", "invalid", "error"]


def insert_reg_request(telegram_user_id: int, sl: int) -> RegInsertResult:
    if sl <= 0:
        return "invalid"
    if has_reg_acc_row_for_user(telegram_user_id):
        return "busy"
    try:
        sb = _get_client()
        sb.table("reg_acc").insert(
            {"sl": sl, "id_tele": _id_tele(telegram_user_id)}
        ).execute()
        return "ok"
    except Exception:
        logger.exception(
            "Không insert reg_acc user_id=%s sl=%s",
            telegram_user_id,
            sl,
        )
        return "error"
