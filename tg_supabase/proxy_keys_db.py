# -*- coding: utf-8 -*-
"""Lưu key proxy theo user vào bảng public.proxy_keys (Supabase).

Cột: telegram_user_id, proxy_type, key_value, label, is_active, created_at, last_used_at.
Mỗi (user, proxy_type) chỉ một bản ghi active: khi lưu mới, các dòng active cũ cùng type bị is_active=false.

DDL mẫu (SQL Editor):

    CREATE TABLE public.proxy_keys (
      id               bigserial PRIMARY KEY,
      telegram_user_id bigint NOT NULL,
      proxy_type       text NOT NULL,
      key_value        text NOT NULL,
      label            text,
      is_active        boolean NOT NULL DEFAULT true,
      created_at       timestamptz NOT NULL DEFAULT now(),
      last_used_at     timestamptz
    );
    CREATE INDEX proxy_keys_user_active_idx
      ON public.proxy_keys (telegram_user_id) WHERE (is_active = true);

Bot dùng anon key: bật RLS và thêm policy INSERT/UPDATE/SELECT/DELETE phù hợp,
hoặc dùng service role (chỉ server) để ghi không cần policy chi tiết.

delete_user_proxies: xóa hẳn mọi bản ghi của user (không chỉ is_active=false).
"""
import logging
from typing import Dict, Optional

from supabase import Client, create_client

from .supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


def save_user_proxy_key(
    user_id: int,
    proxy_type: str,
    key: str,
    label: Optional[str] = None,
) -> None:
    proxy_type = proxy_type.strip()
    key = key.strip()
    if not proxy_type or not key:
        return
    try:
        sb = _get_client()
        existing = (
            sb.table("proxy_keys")
            .select("id")
            .eq("telegram_user_id", user_id)
            .eq("proxy_type", proxy_type)
            .limit(1)
            .execute()
        )

        payload: Dict = {"key_value": key, "is_active": True}
        if label is not None:
            payload["label"] = label

        if existing.data:
            (
                sb.table("proxy_keys")
                .update(payload)
                .eq("telegram_user_id", user_id)
                .eq("proxy_type", proxy_type)
                .execute()
            )
        else:
            row: Dict = {
                "telegram_user_id": user_id,
                "proxy_type": proxy_type,
                **payload,
            }
            sb.table("proxy_keys").insert(row).execute()
    except Exception:
        logger.exception(
            "Không lưu được proxy_keys user_id=%s proxy_type=%s",
            user_id,
            proxy_type,
        )


def get_user_proxy_key(user_id: int, proxy_type: str) -> Optional[str]:
    print(f"get_user_proxy_key: user_id={user_id}, proxy_type={proxy_type}")
    proxy_type = proxy_type.strip()
    if not proxy_type:
        return None
    try:
        sb = _get_client()
        resp = (
            sb.table("proxy_keys")
            .select("key_value")
            .eq("telegram_user_id", user_id)
            .eq("proxy_type", proxy_type)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        print(f"rows:{rows}")
        if not rows:
            return None
        v = rows[0].get("key_value")
        return str(v).strip() if v is not None else None
    except Exception:
        logger.exception(
            "Không đọc được proxy_keys user_id=%s proxy_type=%s",
            user_id,
            proxy_type,
        )
        return None


def get_user_active_proxy_map(user_id: int) -> Dict[str, str]:
    """Mọi proxy_type đang active; nếu trùng type thì lấy bản ghi created_at mới nhất."""
    try:
        sb = _get_client()
        resp = (
            sb.table("proxy_keys")
            .select("proxy_type,key_value")
            .eq("telegram_user_id", user_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .execute()
        )
        rows = resp.data or []
        out: Dict[str, str] = {}
        for row in rows:
            pt = str(row.get("proxy_type") or "").strip()
            kv = str(row.get("key_value") or "").strip()
            if not pt or not kv:
                continue
            if pt not in out:
                out[pt] = kv
        return out
    except Exception:
        logger.exception("Không đọc được proxy map user_id=%s", user_id)
        return {}


def list_user_proxy_keys(user_id: int) -> Dict[str, str]:
    """Giống file JSON cũ: dict proxy_type -> key_value (chỉ active)."""
    return dict(get_user_active_proxy_map(user_id))


def delete_user_proxies(user_id: int) -> bool:
    """Xóa hẳn tất cả dòng proxy_keys của user. Trả False nếu lỗi (RLS, mạng, …)."""
    try:
        sb = _get_client()
        sb.table("proxy_keys").delete().eq("telegram_user_id", user_id).execute()
        return True
    except Exception:
        logger.exception("Không xóa được proxy_keys user_id=%s", user_id)
        return False
