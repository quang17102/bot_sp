# -*- coding: utf-8 -*-
"""Đối soát nạp tiền từ API BIDV và áp dụng quyền lợi."""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

from sieuthicode_token_bidv_get import get_token_bidv
from tg_supabase.deposit_orders import delete_deposit_order, get_active_deposit_orders
from tg_supabase.subscriptions import create_reg_subscription
from tg_supabase.telegram_users_db import increase_user_tien

logger = logging.getLogger(__name__)

_SUBSCRIPTION_CODES = {"reg1", "reg7", "reg30", "sv7", "sv30"}


def _parse_amount_vnd(value: Any) -> int:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _tx_matches_order(tx: dict, order: dict) -> bool:
    payment_code = _normalize_text(order.get("payment_code"))
    if not payment_code:
        return False
    amount_expected = int(order.get("amount") or 0)
    amount_tx = _parse_amount_vnd(tx.get("Amount"))
    if amount_expected <= 0 or amount_tx != amount_expected:
        return False

    desc = _normalize_text(tx.get("Description"))
    remark = _normalize_text(tx.get("Remark"))
    return payment_code in desc or payment_code in remark


def _apply_order(order: dict) -> str:
    user_id = int(order.get("telegram_user_id") or 0)
    package_code = str(order.get("package_code") or "").strip().lower()
    amount = int(order.get("amount") or 0)

    if user_id <= 0 or amount <= 0:
        return "invalid_order"

    if package_code in _SUBSCRIPTION_CODES:
        if create_reg_subscription(user_id, package_code):
            return "reg_subscription"
        return "subscription_failed"

    if package_code.startswith("custom_"):
        if increase_user_tien(user_id, amount):
            return "balance_topup"
        return "topup_failed"

    # Gói khác (vd sv7/sv30) chưa có logic cấp quyền riêng.
    return "unsupported_package"


def reconcile_deposits_once(
    api_token: str,
    on_payment_applied: Optional[Callable[[str], None]] = None,
) -> dict[str, int]:
    """Quét 1 lần: lấy giao dịch BIDV, match deposit_orders, áp dụng quyền lợi."""
    token = (api_token or "").strip()
    if not token:
        return {"orders": 0, "matched": 0, "applied": 0, "deleted": 0}

    resp = get_token_bidv(token, timeout=30.0)
    print(f"resp:{resp}")
    print(f"resp.ok:{resp.text}")
    if not resp.ok:
        logger.warning("TokenBIDV HTTP=%s body=%s", resp.status_code, resp.text[:300])
        return {"orders": 0, "matched": 0, "applied": 0, "deleted": 0}

    try:
        payload = resp.json()
    except Exception:
        logger.warning("TokenBIDV response is not JSON: %s", resp.text[:300])
        return {"orders": 0, "matched": 0, "applied": 0, "deleted": 0}

    txs = payload.get("transactions") or []
    orders = get_active_deposit_orders(limit=300)
    stats = {"orders": len(orders), "matched": 0, "applied": 0, "deleted": 0}

    for order in orders:
        matched_tx = None
        for tx in txs:
            if _tx_matches_order(tx, order):
                matched_tx = tx
                break
        if not matched_tx:
            continue
        stats["matched"] += 1

        action = _apply_order(order)
        if action in {"reg_subscription", "balance_topup"}:
            stats["applied"] += 1
            if delete_deposit_order(int(order["id"])):
                stats["deleted"] += 1
                if on_payment_applied:
                    try:
                        on_payment_applied(str(order.get("payment_code") or ""))
                    except Exception:
                        logger.exception("on_payment_applied callback failed")
        else:
            logger.warning(
                "Deposit matched but not applied (order_id=%s, action=%s)",
                order.get("id"),
                action,
            )

    return stats
