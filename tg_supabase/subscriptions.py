# -*- coding: utf-8 -*-
"""Quản lý gói reg (reg1, reg7, reg30) trong Supabase.

- Bảng `packages`:
    package_code: 'reg1' | 'reg7' | 'reg30'
    name: tên gói hiển thị
    feature: ví dụ 'reg_unlimited'
    duration_days: số ngày hiệu lực
    max_reg_accounts: số acc tối đa (ở đây 100000, coi như unlimited thực tế)

- Bảng `user_subscriptions`:
    telegram_user_id: ID Telegram
    package_code: trùng packages.package_code
    started_at, expires_at, status: quản lý thời hạn gói

Hàm chính:
- ensure_reg_package(package_code): tạo/cập nhật định nghĩa gói.
- create_reg_subscription(telegram_user_id, package_code): gán gói cho user (unlimited theo thời gian).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from supabase import Client, create_client

from tg_supabase.supabase_config import NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL


logger = logging.getLogger(__name__)

_client: Optional[Client] = None
TZ_VN = timezone(timedelta(hours=7))


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)
    return _client


RegCode = Literal["reg1", "reg7", "reg30"]


def ensure_reg_package(package_code: RegCode) -> None:
    """Đảm bảo bản ghi gói reg1/reg7/reg30 tồn tại trong bảng packages."""
    mapping: dict[RegCode, tuple[str, int]] = {
        "reg1": ("Gói REG 1 ngày", 1),
        "reg7": ("Gói REG 7 ngày", 7),
        "reg30": ("Gói REG 30 ngày", 30),
    }
    if package_code not in mapping:
        raise ValueError(f"Unsupported reg package_code: {package_code}")

    name, duration_days = mapping[package_code]
    sb = _get_client()
    # max_reg_accounts = 100000: coi như unlimited về mặt business.
    try:
        sb.table("packages").upsert(
            {
                "code": package_code,
                "name": name,
                "feature": "reg_unlimited",
                "duration_days": duration_days,
                "max_reg_accounts": 100000,
            },
            on_conflict="package_code",
        ).execute()
    except Exception:
        logger.exception("Không upsert được packages cho package_code=%s", package_code)


def create_reg_subscription(telegram_user_id: int, package_code: RegCode) -> None:
    """Tạo gói reg unlimited cho user với mã reg1/reg7/reg30.

    - Nếu đã có gói active cùng loại, cộng dồn thêm ngày (extend expires_at).
    - Nếu chưa có, tạo mới với started_at=now, expires_at=now+duration_days.
    """
    sb = _get_client()
    now = datetime.now(TZ_VN)

    try:
        # Lấy thông tin gói từ bảng packages để lấy duration_days
        pkg_resp = (
            sb.table("packages")
            .select("code,name,duration_days,max_reg_accounts")
            .eq("code", package_code)
            .limit(1)
            .execute()
        )
        pkg_rows = pkg_resp.data or []
        if not pkg_rows:
            raise ValueError(f"Package không tồn tại: {package_code}")

        pkg = pkg_rows[0]
        duration_days = int(pkg["duration_days"])

        # Tìm subscription active mới nhất của user cho gói reg (cùng package_code)
        resp = (
            sb.table("user_subscriptions")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .eq("package_code", package_code)
            .eq("status", "active")
            .order("expires_at", desc=True)
            .limit(1)
            .execute()
        )
        data = resp.data or []

        if data:
            current = data[0]
            current_expires = datetime.fromisoformat(
                current["expires_at"].replace("Z", "+00:00")
            )
            # Nếu còn hạn, cộng dồn; nếu hết hạn thì bắt đầu từ now.
            base = current_expires if current_expires > now else now
            new_expires = base + timedelta(days=duration_days)
            sb.table("user_subscriptions").update(
                {"expires_at": new_expires.isoformat()}
            ).eq("id", current["id"]).execute()
        else:
            new_expires = now + timedelta(days=duration_days)
            sb.table("user_subscriptions").insert(
                {
                    "telegram_user_id": telegram_user_id,
                    "package_code": package_code,
                    "started_at": now.isoformat(),
                    "expires_at": new_expires.isoformat(),
                    "status": "active",
                    "source": "manual",
                }
            ).execute()
    except Exception:
        logger.exception(
            "Không tạo/cập nhật reg subscription cho user=%s, package_code=%s",
            telegram_user_id,
            package_code,
        )


def get_active_reg_subscriptions(telegram_user_id: int) -> list[dict]:
    """Lấy danh sách các gói reg active của một user.

    Trả về list các dict có ít nhất:
    - package_code
    - started_at
    - expires_at
    - status
    """
    sb = _get_client()
    try:
        resp = (
            sb.table("user_subscriptions")
            .select("package_code,started_at,expires_at,status")
            .eq("telegram_user_id", telegram_user_id)
            .eq("status", "active")
            .in_("package_code", ["reg1", "reg7", "reg30"])
            .order("expires_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception:
        logger.exception(
            "Không lấy được active reg subscriptions cho user=%s", telegram_user_id
        )
        return []


def main():
    create_reg_subscription(1204125067, "reg1")
if __name__ == "__main__":
    main()