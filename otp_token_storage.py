import logging
from typing import Dict, Optional

from supabase import Client, create_client

from tg_supabase.supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


def save_user_otp_token(user_id: int, provider: str, token: str) -> None:
    provider = (provider or "").strip().lower()
    token = (token or "").strip()
    if not provider or not token:
        return
    try:
        sb = _get_client()
        sb.table("otp_provider_tokens").upsert(
            {
                "telegram_user_id": int(user_id),
                "provider": provider,
                "token": token,
            },
            on_conflict="telegram_user_id,provider",
        ).execute()
    except Exception:
        logger.exception("Không lưu được OTP token cho user=%s provider=%s", user_id, provider)


def get_user_otp_token(user_id: int, provider: str) -> Optional[str]:
    provider = (provider or "").strip().lower()
    if not provider:
        return None
    try:
        sb = _get_client()
        resp = (
            sb.table("otp_provider_tokens")
            .select("token")
            .eq("telegram_user_id", int(user_id))
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        return str(rows[0].get("token") or "").strip() or None
    except Exception:
        logger.exception("Không lấy được OTP token cho user=%s provider=%s", user_id, provider)
        return None


def list_user_otp_tokens(user_id: int) -> Dict[str, str]:
    try:
        sb = _get_client()
        resp = (
            sb.table("otp_provider_tokens")
            .select("provider,token")
            .eq("telegram_user_id", int(user_id))
            .execute()
        )
        rows = resp.data or []
        return {
            str(row.get("provider") or "").strip().lower(): str(row.get("token") or "")
            for row in rows
            if row.get("provider")
        }
    except Exception:
        logger.exception("Không lấy được danh sách OTP token cho user=%s", user_id)
        return {}


def delete_all_user_otp_tokens(user_id: int) -> bool:
    existing = list_user_otp_tokens(user_id)
    if not existing:
        return False
    try:
        sb = _get_client()
        sb.table("otp_provider_tokens").delete().eq("telegram_user_id", int(user_id)).execute()
        return True
    except Exception:
        logger.exception("Không xóa được OTP token cho user=%s", user_id)
        return False
