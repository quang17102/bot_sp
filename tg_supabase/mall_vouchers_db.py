# -*- coding: utf-8 -*-
"""CRUD voucher mall (danh sách voucher) trên Supabase.

Bảng gợi ý: public.mall_vouchers
  - id (bigserial PK)
  - ten_ma (text)
  - promotionid (bigint)
  - voucher_code (text)
  - signature (text)
  - created_at (timestamptz default now())
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from supabase import Client, create_client

from .supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


def add_mall_voucher(
    ten_ma: str,
    promotionid: int,
    voucher_code: str,
    signature: str,
) -> bool:
    """Thêm 1 voucher vào bảng mall_vouchers."""
    try:
        sb = _get_client()
        sb.table("mall_vouchers").insert(
            {
                "ten_ma": (ten_ma or "").strip(),
                "promotionid": int(promotionid),
                "voucher_code": (voucher_code or "").strip(),
                "signature": (signature or "").strip(),
            }
        ).execute()
        return True
    except Exception:
        logger.exception(
            "Không add voucher vào mall_vouchers (promotionid=%s, voucher_code=%s)",
            promotionid,
            voucher_code,
        )
        return False


def list_mall_vouchers(limit: int = 200) -> list[dict[str, Any]]:
    """Lấy danh sách voucher mall (mới nhất trước)."""
    sb = _get_client()
    try:
        resp = (
            sb.table("mall_vouchers")
            .select("id,ten_ma,promotionid,voucher_code,signature,created_at")
            .order("id", desc=True)
            .limit(int(limit))
            .execute()
        )
        return resp.data or []
    except Exception:
        logger.exception("Không list được mall_vouchers")
        return []


def delete_mall_voucher(voucher_id: int) -> bool:
    """Xóa 1 voucher theo id."""
    sb = _get_client()
    try:
        sb.table("mall_vouchers").delete().eq("id", int(voucher_id)).execute()
        return True
    except Exception:
        logger.exception("Không xóa được mall_vouchers id=%s", voucher_id)
        return False

