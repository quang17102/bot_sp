# -*- coding: utf-8 -*-
"""
Xem trạng thái voucher Shopee — gọi API mall get_voucher_detail.

Đầu vào: promotionid, voucher_code, signature (bắt buộc);
         cookie mall (SPC_ST / Cookie đầy đủ) — **có thể để rỗng** nếu không cần.

Batch: đa luồng; in mặc định dạng **thẻ** (🎫 💰 📊 📥 ⏳): ``ten_ma`` = dòng Giảm;
``Đơn`` = ``min_spend``; Đã dùng = ``percentage_used``; Lượt lưu: ``percentage_claimed`` ∈ {1, 100} → hết lượt;
Hiệu lực tạm = ``start_time``. ``--tsv`` = bảng tab.

List mặc định: **VOUCHER_BATCH_LIST_HARDCODED** — ``python voucher_status.py batch`` (không ``-i``).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import requests

DEFAULT_URL = "https://mall.shopee.vn/api/v2/voucher_wallet/get_voucher_detail"
DEFAULT_BATCH_WORKERS = 12

# Phân cách giữa các voucher trong batch (in CLI + Telegram)
VOUCHER_BATCH_SEPARATOR = "\n──────────────────\n"

# Đầu vào batch mặc định — promotionid, voucher_code, signature; tùy chọn **ten_ma** (tên mã hiển thị).
# Khi chạy: `python voucher_status.py batch` (không cần -i) sẽ dùng list này.
VOUCHER_BATCH_LIST_HARDCODED: List[Dict[str, Any]] = [
    {
        "ten_ma": "100.000đ | Đơn 0đ",
        "promotionid": 1365690377211904,
        "voucher_code": "CRMNUICL80T3",
        "signature": "b3ca10e3fa0e469b3c52577083cb3ee617ec2d40dd6ad1a3130609050d296c93",
    },
    {
        "ten_ma": "100.000đ | Đơn 0đ",
        "promotionid": 1364961121046528,
        "voucher_code": "CRM19032503NBCP80K",
        "signature": "3e4dc9053e0511d842d8faca0f42ec2b8c9afa204ac5aa91848478216260a050",
    },
    {
        "ten_ma": "100.000đ | Đơn 0đ",
        "promotionid": 1364240113766400,
        "voucher_code": "Q1JNTlVJQ0xIQ01UMw",
        "signature": "b0f1cf1ee9828007ab7a0a999df1d5c9bb2c9168afef559a60da79aa31c70451",
    },
    # {
    #     "ten_ma": "Giảm: 80.000đ | Đơn 0đ",
    #     "promotionid": 1375377811214336,
    #     "voucher_code": "CRMNUIIZCL80T3V3",
    #     "signature": "99dea321442ee33761d01b7c2e578b3c9656eb7089c6df811bd66562e39cf58e",
    # },
    {
        "ten_ma": "80.000đ | Đơn 0đ",
        "promotionid": 1364240045477888,
        "voucher_code": "CRMNUIDP80T3",
        "signature": "b3d419fc12e103249ea8ffcee7a596d61235bda334aec0f991711c4bade69d87",
    },
    {
        "ten_ma": "Tối đa 500.000 ₫",
        "promotionid": 1363693662932996,
        "voucher_code": "FSV-1363693662932996",
        "signature": "6688290d7df8e513c74249bdfc8d43168fc1c8065e7461f3bad2ea92a4cb0483",
    },
]

DEFAULT_HEADERS_BASE = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Host": "mall.shopee.vn",
    "cache-control": "no-cache",
    "User-Agent": "Android app Shopee appver=28320 app_type=1",
    "x-api-source": "rn",
    "x-sap-type": "2",
    "X-Shopee-Client-Timezone": "Asia/Ho_Chi_Minh",
    "referer": "https://mall.shopee.vn/",
}


def _ts(value: Any) -> str:
    if value is None:
        return ""
    try:
        return datetime.fromtimestamp(int(value)).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return str(value)


def _normalize_promotion_id(promotionid: Union[int, str]) -> int:
    if isinstance(promotionid, int):
        return promotionid
    s = str(promotionid).strip()
    return int(s)


def build_payload(
    promotionid: Union[int, str],
    voucher_code: str,
    signature: str,
    *,
    need_basic_info: bool = True,
    need_user_voucher_status: bool = True,
) -> Dict[str, Any]:
    return {
        "promotionid": _normalize_promotion_id(promotionid),
        "voucher_code": str(voucher_code).strip(),
        "signature": str(signature).strip(),
        "need_basic_info": need_basic_info,
        "need_user_voucher_status": need_user_voucher_status,
    }


def build_headers(cookie: str) -> Dict[str, str]:
    """Cookie mall (có thể rỗng — khi rỗng không gửi header Cookie)."""
    h = dict(DEFAULT_HEADERS_BASE)
    raw = (cookie or "").strip()
    if not raw:
        return h
    if "SPC_ST=" in raw or ";" in raw:
        h["Cookie"] = raw
    else:
        h["Cookie"] = f"SPC_ST={raw}"
    return h


def fetch_voucher_detail(
    promotionid: Union[int, str],
    voucher_code: str,
    signature: str,
    cookie: str = "",
    *,
    url: str = DEFAULT_URL,
    timeout: float = 20.0,
    proxies: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Gọi API get_voucher_detail. Cookie có thể rỗng.
    ``proxies`` có thể ``None`` / không truyền — gọi trực tiếp không qua proxy; dict rỗng cũng bỏ qua.

    Returns:
        (data_json, None) nếu HTTP 200 và parse JSON được;
        (None, error_message) nếu lỗi mạng / HTTP lỗi / JSON lỗi.
    """
    payload = build_payload(promotionid, voucher_code, signature)
    headers = build_headers(cookie)

    req_kw: Dict[str, Any] = {
        "url": url,
        "headers": headers,
        "json": payload,
        "timeout": timeout,
    }
    if proxies and isinstance(proxies, dict) and len(proxies) > 0:
        req_kw["proxies"] = proxies

    try:
        resp = requests.post(**req_kw)
    except requests.RequestException as exc:
        return None, f"Lỗi kết nối: {exc}"

    try:
        data = resp.json()
    except ValueError:
        return None, f"Không parse được JSON (HTTP {resp.status_code}): {resp.text[:500]}"

    if resp.status_code >= 400:
        err_hint = ""
        if resp.status_code in (401, 403):
            err_hint = " (cookie hết hạn hoặc bị từ chối?)"
        return data, f"HTTP {resp.status_code}{err_hint}"

    return data, None


# ----- Batch đa luồng -----


@dataclass
class VoucherItem:
    """Một dòng đầu vào cho API (promotionid + voucher_code + signature; tùy chọn ten_ma)."""

    promotionid: Union[int, str]
    voucher_code: str
    signature: str
    ten_ma: Optional[str] = None

    @classmethod
    def from_mapping(cls, d: Dict[str, Any]) -> Optional["VoucherItem"]:
        pid = d.get("promotionid")
        if pid is None:
            pid = d.get("promotion_id")
        vc = d.get("voucher_code")
        sig = d.get("signature")
        if pid is None or vc is None or sig is None:
            return None
        ten = d.get("ten_ma")
        if ten is None:
            ten = d.get("name") or d.get("label")
        ten_str = str(ten).strip() if ten is not None else None
        if ten_str == "":
            ten_str = None
        return cls(
            promotionid=pid,
            voucher_code=str(vc).strip(),
            signature=str(sig).strip(),
            ten_ma=ten_str,
        )


def normalize_voucher_items(
    items: Sequence[Union[VoucherItem, Dict[str, Any]]],
) -> List[VoucherItem]:
    out: List[VoucherItem] = []
    for i, raw in enumerate(items):
        if isinstance(raw, VoucherItem):
            out.append(raw)
            continue
        if isinstance(raw, dict):
            v = VoucherItem.from_mapping(raw)
            if v:
                out.append(v)
            else:
                raise ValueError(f"Dòng {i}: thiếu promotionid / voucher_code / signature")
        else:
            raise TypeError(f"Dòng {i}: kiểu không hợp lệ: {type(raw)}")
    return out


def extract_voucher_summary_fields(api_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lấy voucher_code, percentage_claimed, percentage_used, start_time, min_spend
    từ body JSON trả về của get_voucher_detail.
    """
    vb = ((api_json.get("data") or {}).get("voucher_basic_info")) or {}
    if not isinstance(vb, dict):
        vb = {}
    st = vb.get("start_time")
    return {
        "voucher_code": vb.get("voucher_code"),
        "percentage_claimed": vb.get("percentage_claimed"),
        "percentage_used": vb.get("percentage_used"),
        "min_spend": vb.get("min_spend"),
        "start_time": _ts(st),
        "start_time_raw": st,
        "promotionid": vb.get("promotionid"),
        "shopee_error": api_json.get("error"),
    }


def _fetch_one_summary_row(
    item: VoucherItem,
    cookie: str,
    url: str,
    timeout: float,
    proxies: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Một request — chạy trong thread pool."""
    base = {
        "ten_ma": item.ten_ma or "",
        "input_promotionid": item.promotionid,
        "input_voucher_code": item.voucher_code,
        "voucher_code": None,
        "percentage_claimed": None,
        "percentage_used": None,
        "min_spend": None,
        "start_time": "",
        "start_time_raw": None,
        "promotionid": None,
        "shopee_error": None,
        "http_warning": None,
        "fetch_error": None,
    }
    data, err = fetch_voucher_detail(
        item.promotionid,
        item.voucher_code,
        item.signature,
        cookie,
        url=url,
        timeout=timeout,
        proxies=proxies,
    )
    if data is None:
        base["fetch_error"] = err
        return base

    summ = extract_voucher_summary_fields(data)
    base.update(
        {
            "voucher_code": summ.get("voucher_code"),
            "percentage_claimed": summ.get("percentage_claimed"),
            "percentage_used": summ.get("percentage_used"),
            "min_spend": summ.get("min_spend"),
            "start_time": summ.get("start_time"),
            "start_time_raw": summ.get("start_time_raw"),
            "promotionid": summ.get("promotionid"),
            "shopee_error": summ.get("shopee_error"),
        }
    )
    if err:
        base["http_warning"] = err
    return base


def fetch_voucher_batch_parallel(
    items: Sequence[Union[VoucherItem, Dict[str, Any]]],
    cookie: str = "",
    *,
    max_workers: int = DEFAULT_BATCH_WORKERS,
    url: str = DEFAULT_URL,
    timeout: float = 20.0,
    proxies: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Gọi get_voucher_detail song song cho từng phần tử.

    Mỗi phần tử dict cần: promotionid (hoặc promotion_id), voucher_code, signature;
    tùy chọn: **ten_ma** (hoặc name / label) — hiển thị trong kết quả batch.

    Trả về list dict (cùng thứ tự `items`), gồm các field summary + lỗi từng dòng nếu có.
    ``proxies`` có thể ``None`` — không dùng proxy.
    """
    normalized = normalize_voucher_items(items)
    if not normalized:
        return []

    n = len(normalized)
    results: List[Optional[Dict[str, Any]]] = [None] * n

    def worker(index: int, item: VoucherItem) -> Tuple[int, Dict[str, Any]]:
        row = _fetch_one_summary_row(item, cookie, url, timeout, proxies=proxies)
        return index, row

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, n))) as pool:
        futs = [
            pool.submit(worker, i, normalized[i]) for i in range(n)
        ]
        for fut in as_completed(futs):
            idx, row = fut.result()
            results[idx] = row

    return [r for r in results if r is not None]


def load_voucher_list_from_json(path: str) -> List[Dict[str, Any]]:
    """Đọc file JSON: mảng [...] các object có promotionid, voucher_code, signature; tùy chọn ten_ma."""
    p = os.path.expanduser(path)
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "vouchers" in data:
        data = data["vouchers"]
    if not isinstance(data, list):
        raise ValueError("JSON phải là mảng [...] hoặc object có key 'vouchers'")
    return [x for x in data if isinstance(x, dict)]


def _format_vnd_mall(value: Any) -> str:
    """
    Định dạng min_spend (API Shopee mall thường là bội số nhỏ; chia 100000 → VND như checkmvd).
    """
    if value in (None, ""):
        return "0"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    vnd = v / 100_000.0
    return f"{int(round(vnd)):,}".replace(",", ".")


def _format_percent_used_display(pu: Any) -> str:
    if pu is None:
        return "—"
    try:
        x = float(pu)
    except (TypeError, ValueError):
        return str(pu)
    if 0 <= x <= 1.0001:
        x = x * 100.0
    return f"{int(round(x))}%"


def _emoji_da_dung(pu: Any) -> str:
    try:
        x = float(pu)
        if 0 <= x <= 1.0001:
            x = x * 100.0
        if x >= 90:
            return "🔴"
        return "🟢"
    except (TypeError, ValueError):
        return ""


def _luot_luu_label(pc: Any) -> str:
    """percentage_claimed == 1 (hoặc 100) → Đã hết lượt; ngược lại Còn lượt."""
    if pc is None:
        return "—"
    try:
        f = float(pc)
    except (TypeError, ValueError):
        return "—"
    if abs(f - 1.0) < 1e-9 or abs(f - 100.0) < 1e-9:
        return "Đã hết lượt"
    return "Còn lượt"


def format_voucher_card_text(row: Dict[str, Any]) -> str:
    """
    Hiển thị dạng thẻ (Telegram-style):
      🎫 mã
      💰 Giảm: tên mã (ten_ma) | Đơn …đ
      📊 Đã dùng: % 🔴/🟢
      📥 Lượt lưu: Đã hết lượt / Còn lượt
      ⏳ Hiệu lực: start_time (tạm)
    """
    if row.get("fetch_error"):
        name = row.get("ten_ma") or row.get("input_voucher_code") or "?"
        return f"❌ {name}\n{row['fetch_error']}"

    err_api = row.get("shopee_error")
    if err_api not in (None, 0):
        name = row.get("ten_ma") or row.get("voucher_code") or "?"
        return f"⚠️ {name}\nShopee error: {err_api}"

    code = row.get("voucher_code") or row.get("input_voucher_code") or "—"
    ten = (row.get("ten_ma") or "").strip() or str(code)
    min_sp = _format_vnd_mall(row.get("min_spend"))
    pu = row.get("percentage_used")
    pu_str = _format_percent_used_display(pu)
    em = _emoji_da_dung(pu)
    luot = _luot_luu_label(row.get("percentage_claimed"))
    hieu_luc = row.get("start_time") or "—"

    line3 = f"📊 Đã dùng: {pu_str}"
    if em:
        line3 = f"{line3} {em}"

    lines = [
        f"🎫 {code}",
        f"💰 Giảm: {ten}",
        line3,
        f"📥 Lượt lưu: {luot}",
        f"⏳ Hiệu lực: {hieu_luc}",
    ]
    if row.get("http_warning"):
        lines.append(f"⚠️ {row['http_warning']}")
    return "\n".join(lines)


def format_voucher_card_telegram_html_block(row: Dict[str, Any]) -> str:
    """
    Một thẻ voucher cho Telegram (parse_mode HTML).
    Dòng **Giảm** + **ten_ma** bọc trong ``<b>Giảm: …</b>`` (không escape thẻ b).
    """
    if row.get("fetch_error"):
        name = row.get("ten_ma") or row.get("input_voucher_code") or "?"
        return html.escape(f"❌ {name}\n{row['fetch_error']}")

    err_api = row.get("shopee_error")
    if err_api not in (None, 0):
        name = row.get("ten_ma") or row.get("voucher_code") or "?"
        return html.escape(f"⚠️ {name}\nShopee error: {err_api}")

    code = row.get("voucher_code") or row.get("input_voucher_code") or "—"
    ten = (row.get("ten_ma") or "").strip() or str(code)
    min_sp = _format_vnd_mall(row.get("min_spend"))
    pu = row.get("percentage_used")
    pu_str = _format_percent_used_display(pu)
    em = _emoji_da_dung(pu)
    luot = _luot_luu_label(row.get("percentage_claimed"))
    hieu_luc = row.get("start_time") or "—"

    line1 = html.escape(f"🎫 {code}")
    # In đậm "Giảm:" + tên mã (ten_ma); phần | Đơn …đ plain (đã an toàn)
    line2 = (
        "💰 "
        f"<b>Giảm: {html.escape(ten)}</b>"
    )

    line3 = html.escape(f"📊 Đã dùng: {pu_str}")
    if em:
        line3 = line3 + " " + em  # emoji không cần escape

    lines = [
        line1,
        line2,
        line3,
        html.escape(f"📥 Lượt lưu: {luot}"),
        html.escape(f"⏳ Hiệu lực: {hieu_luc}"),
    ]
    if row.get("http_warning"):
        lines.append(html.escape(f"⚠️ {row['http_warning']}"))
    return "\n".join(lines)


def format_batch_cards(rows: Sequence[Dict[str, Any]]) -> str:
    """Nối nhiều thẻ voucher, cách nhau bằng ``VOUCHER_BATCH_SEPARATOR``."""
    return VOUCHER_BATCH_SEPARATOR.join(format_voucher_card_text(r) for r in rows)


def format_batch_cards_telegram_html(rows: Sequence[Dict[str, Any]]) -> str:
    """
    Một tin nhắn HTML cho Telegram.
    Dùng ``\\n`` xuống dòng; **Giảm + ten_ma** in đậm qua ``format_voucher_card_telegram_html_block``.
    """
    if not rows:
        return ""
    blocks = [format_voucher_card_telegram_html_block(r) for r in rows]
    return "<b>📋 Danh sách voucher</b>\n\n" + VOUCHER_BATCH_SEPARATOR.join(blocks)


def format_batch_table(rows: Sequence[Dict[str, Any]]) -> str:
    """Bảng TSV (debug / --tsv)."""
    lines = [
        "ten_ma\tvoucher_code\tpercentage_claimed\tpercentage_used\tstart_time\tnotes",
        "-" * 96,
    ]
    for r in rows:
        notes = []
        if r.get("fetch_error"):
            notes.append(str(r["fetch_error"]))
        if r.get("http_warning"):
            notes.append(str(r["http_warning"]))
        if r.get("shopee_error") not in (None, 0):
            notes.append(f"error={r['shopee_error']}")
        line = "\t".join(
            [
                str(r.get("ten_ma") or ""),
                str(r.get("voucher_code") or ""),
                str(r.get("percentage_claimed") if r.get("percentage_claimed") is not None else ""),
                str(r.get("percentage_used") if r.get("percentage_used") is not None else ""),
                str(r.get("start_time") or ""),
                "; ".join(notes),
            ]
        )
        lines.append(line)
    return "\n".join(lines)


def format_voucher_basic_block(vb: Dict[str, Any]) -> str:
    lines = [
        "========== Voucher (basic) ==========",
        f"promotionid: {vb.get('promotionid')}",
        f"voucher_code: {vb.get('voucher_code')}",
        f"use_type: {vb.get('use_type')}",
        f"voucher_market_type: {vb.get('voucher_market_type')}",
        f"min_spend: {vb.get('min_spend')}",
        f"wallet_redeemable: {vb.get('wallet_redeemable')}",
        f"new_user_only: {vb.get('new_user_only')}",
        f"percentage_claimed: {vb.get('percentage_claimed')}",
        f"percentage_used: {vb.get('percentage_used')}",
        f"start_time: {_ts(vb.get('start_time'))}",
        f"end_time: {_ts(vb.get('end_time'))}",
    ]
    if vb.get("sub_icon_text"):
        lines.append(f"sub_icon_text: {vb.get('sub_icon_text')}")
    if vb.get("description"):
        desc = str(vb.get("description") or "")
        lines.append(f"description: {desc[:250]}{'...' if len(desc) > 250 else ''}")
    lines.append("=====================================")
    return "\n".join(lines)


def format_user_voucher_status_block(status: Any) -> str:
    """In trạng thái voucher phía user (cấu trúc tùy API)."""
    if status is None:
        return ""
    if isinstance(status, dict):
        pretty = json.dumps(status, ensure_ascii=False, indent=2)
    else:
        pretty = str(status)
    return (
        "\n========== Trạng thái voucher (user) ==========\n"
        f"{pretty}\n"
        "================================================"
    )


def format_voucher_detail_response(obj: Dict[str, Any]) -> str:
    """Chuỗi tóm tắt từ response JSON đầy đủ."""
    parts: list[str] = []
    parts.append(f"error: {obj.get('error')}")

    data = obj.get("data") if isinstance(obj.get("data"), dict) else {}
    vb = data.get("voucher_basic_info") if isinstance(data, dict) else None
    if isinstance(vb, dict) and vb:
        parts.append(format_voucher_basic_block(vb))
    else:
        parts.append("(không có voucher_basic_info)")

    if isinstance(data, dict) and "user_voucher_status" in data:
        parts.append(format_user_voucher_status_block(data.get("user_voucher_status")))

    return "\n".join(parts)


def print_voucher_detail(obj: Any) -> None:
    """In ra stdout (CLI / test)."""
    if not isinstance(obj, dict):
        print("Response (non-dict):", str(obj)[:4000])
        return
    print(format_voucher_detail_response(obj))


def xem_trang_thai_voucher(
    promotionid: Union[int, str],
    voucher_code: str,
    signature: str,
    cookie: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Hàm tiện dùng cho bot / module khác: trả (json, lỗi_http_or_none).

    cookie: tùy chọn; mặc định lấy từ SHOPEE_MALL_COOKIE, có thể rỗng.
    """
    ck = (cookie or os.getenv("SHOPEE_MALL_COOKIE") or "").strip()
    data, err = fetch_voucher_detail(promotionid, voucher_code, signature, ck)
    return data, err


def run_cli(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Voucher mall: một voucher hoặc batch đa luồng.",
    )
    sub = p.add_subparsers(dest="cmd", required=False)

    p_one = sub.add_parser("one", help="Một voucher (get_voucher_detail)")
    p_one.add_argument("--promotionid", required=True, help="Promotion ID")
    p_one.add_argument("--voucher-code", required=True, dest="voucher_code")
    p_one.add_argument("--signature", required=True)
    p_one.add_argument(
        "--cookie",
        default=os.getenv("SHOPEE_MALL_COOKIE", ""),
        help="Cookie mall; có thể rỗng. Env: SHOPEE_MALL_COOKIE",
    )
    p_one.add_argument("--url", default=DEFAULT_URL)

    p_batch = sub.add_parser(
        "batch",
        help="Danh sách voucher — API đa luồng (mặc định: VOUCHER_BATCH_LIST_HARDCODED trong file)",
    )
    p_batch.add_argument(
        "--input",
        "-i",
        default=None,
        help="File JSON [...] — nếu không truyền thì dùng list hardcode VOUCHER_BATCH_LIST_HARDCODED",
    )
    p_batch.add_argument(
        "--cookie",
        default=os.getenv("SHOPEE_MALL_COOKIE", ""),
        help="Cookie mall; có thể rỗng",
    )
    p_batch.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_BATCH_WORKERS,
        help=f"Số luồng tối đa (mặc định {DEFAULT_BATCH_WORKERS})",
    )
    p_batch.add_argument(
        "--json-out",
        action="store_true",
        help="In kết quả dạng JSON ra stdout thay vì thẻ text",
    )
    p_batch.add_argument(
        "--tsv",
        action="store_true",
        help="In bảng TSV thay vì định dạng thẻ emoji (mặc định: thẻ)",
    )
    p_batch.add_argument("--url", default=DEFAULT_URL)

    args = p.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not args.cmd:
        p.print_help()
        return 2

    if args.cmd == "one":
        data, err = fetch_voucher_detail(
            args.promotionid,
            args.voucher_code,
            args.signature,
            args.cookie,
            url=args.url,
        )
        if data is None:
            print(err or "Lỗi không xác định", file=sys.stderr)
            return 1
        print_voucher_detail(data)
        if err:
            print(f"\n[Cảnh báo] {err}", file=sys.stderr)
        return 0

    if args.cmd == "batch":
        if getattr(args, "input", None):
            raw_list = load_voucher_list_from_json(args.input)
        else:
            raw_list = list(VOUCHER_BATCH_LIST_HARDCODED)
        rows = fetch_voucher_batch_parallel(
            raw_list,
            cookie=args.cookie,
            max_workers=args.workers,
            url=args.url,
        )
        if args.json_out:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.tsv:
            print(format_batch_table(rows))
        else:
            print(format_batch_cards(rows))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
