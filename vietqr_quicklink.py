# -*- coding: utf-8 -*-
"""
VietQR Quick Link — URL ảnh QR theo img.vietqr.io.

https://img.vietqr.io/image/<BANK_ID>-<ACCOUNT_NO>-<TEMPLATE>.<ext>?amount=...&addInfo=...&accountName=...
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional
from urllib.parse import quote, urlencode

BASE_URL = "https://img.vietqr.io/image"
DEFAULT_EXTENSION = "png"
_ALLOWED_EXT = frozenset({"png", "jpg", "jpeg", "webp"})


def _keep_letters_numbers_spaces(s: str) -> str:
    """Giữ chữ (Unicode), số, khoảng trắng — bỏ ký tự đặc biệt."""
    out: list[str] = []
    for ch in s:
        if ch.isspace():
            out.append(" ")
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N"):
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _sanitize_add_info(text: str, max_len: int = 50) -> str:
    """Nội dung CK: tối đa 50 ký tự, không ký tự đặc biệt."""
    return _keep_letters_numbers_spaces((text or "").strip())[:max_len]


def _sanitize_account_name(text: str, max_len: int = 70) -> str:
    """Tên thụ hưởng hiển thị trên ảnh (query string)."""
    return _keep_letters_numbers_spaces((text or "").strip())[:max_len]


def build_vietqr_quicklink(
    bank_id: str,
    account_no: str,
    template: str,
    *,
    amount: Optional[int] = None,
    add_info: str = "",
    account_name: str = "",
    extension: str = DEFAULT_EXTENSION,
) -> str:
    """
    Trả về URL Quick Link VietQR.

    bank_id: BIN / short_name / code (vd. 970415, vietinbank, ICB).
    account_no: tối đa 19 ký tự (chữ/số theo quy ước VietQR).
    template: compact | compact2 | qr_only | print | template tùy chỉnh.
    amount: số dương, tối đa 13 chữ số; None = không thêm query amount.
    """
    bid = (bank_id or "").strip()
    acc = (account_no or "").strip()
    tpl = (template or "").strip()
    if not bid or not acc or not tpl:
        raise ValueError("bank_id, account_no và template là bắt buộc")

    acc_clean = re.sub(r"\s+", "", acc)
    if len(acc_clean) > 19:
        raise ValueError("account_no vượt quá 19 ký tự")

    ext = (extension or DEFAULT_EXTENSION).lstrip(".").lower()
    if ext not in _ALLOWED_EXT:
        raise ValueError(f"extension không hỗ trợ: {ext}")

    path = f"{BASE_URL}/{bid}-{acc_clean}-{tpl}.{ext}"
    params: dict[str, str] = {}

    if amount is not None:
        if amount <= 0:
            raise ValueError("amount phải là số dương")
        amt_str = str(amount)
        if len(amt_str) > 13:
            raise ValueError("amount tối đa 13 chữ số")
        params["amount"] = amt_str

    desc = _sanitize_add_info(add_info)
    if desc:
        params["addInfo"] = desc

    name = _sanitize_account_name(account_name)
    if name:
        params["accountName"] = name

    if not params:
        return path
    q = urlencode(params, quote_via=quote, safe="")
    return f"{path}?{q}"


def example_vietinbank() -> str:
    """Ví dụ theo tài liệu VietQR (compact2 + jpg như demo)."""
    return build_vietqr_quicklink(
        "Vietcombank",
        "1066550795",
        "compact2",
        amount=10000,
        add_info="reg1",
        account_name="Huỳnh Quang Duy",
        extension="jpg",
    )


if __name__ == "__main__":
    print(example_vietinbank())
