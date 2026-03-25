# -*- coding: utf-8 -*-
"""
SPX VN — gọi API get_order_info và format lịch sử giao hàng (dùng cho bot & CLI).

Package: ``shipping``
"""

from __future__ import annotations

import html as html_lib
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


def _html(s: str) -> str:
    return html_lib.escape(str(s or ""), quote=False)

SPX_GET_ORDER_INFO = "https://spx.vn/shipment/order/open/order/get_order_info"

# Việt Nam UTC+7, không DST — dùng offset cố định (Windows không cần tzdata)
_TZ_VN = timezone(timedelta(hours=7))

# Phân cách giữa các mốc (form chuẩn)
HISTORY_SEP = "─ ─ ─ ─ ─ ─ ─ ─ ─ ─"

# Telegram Bot API: tối đa 4096 ký tự / tin nhắn text
TELEGRAM_MAX_MESSAGE_CHARS = 4096

# Mã vận đơn: bắt đầu SPX hoặc VN, chữ/số/gạch (token đầu dòng; cùng API get_order_info)
SPX_TRACKING_RE = re.compile(
    r"^(?:SPX|VN)[A-Za-z0-9\-]+",
    re.IGNORECASE,
)

_DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "vi,en-US;q=0.9,en;q=0.8",
    "priority": "u=1, i",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
}


def extract_spx_tracking_from_text(text: str) -> Optional[str]:
    """Lấy mã vận đơn từ tin nhắn (dòng bắt đầu bằng SPX hoặc VN)."""
    if not text:
        return None
    m = SPX_TRACKING_RE.match(text.strip())
    return m.group(0) if m else None


def split_telegram_chunks(text: str, max_len: int = 4000) -> List[str]:
    """Chia text theo độ dài (giới hạn Telegram ~4096). Bot dùng ``format_spx_delivery_history(..., max_chars=...)`` thay vì hàm này."""
    text = text or ""
    if len(text) <= max_len:
        return [text] if text else [""]
    lines = text.split("\n")
    out: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for line in lines:
        need = len(line) + (1 if cur else 0)
        if need > max_len:
            if cur:
                out.append("\n".join(cur))
                cur = []
                cur_len = 0
            for i in range(0, len(line), max_len):
                out.append(line[i : i + max_len])
            continue
        if cur_len + need > max_len and cur:
            out.append("\n".join(cur))
            cur = [line]
            cur_len = len(line)
        else:
            cur.append(line)
            cur_len += need
    if cur:
        out.append("\n".join(cur))
    return out


def get_order_info_spx(
    spx_tn: str,
    *,
    language_code: str = "vi",
    cookie: str = "",
    timeout: float = 25.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    GET get_order_info?spx_tn=...&language_code=vi
    """
    spx_tn = (spx_tn or "").strip()
    if not spx_tn:
        return None, "Thiếu mã spx_tn"

    params = {"spx_tn": spx_tn, "language_code": language_code}
    headers = dict(_DEFAULT_HEADERS)
    headers["referer"] = f"https://spx.vn/track?{spx_tn}"

    ck = (cookie or os.getenv("SPX_COOKIE", "")).strip()
    if ck:
        headers["Cookie"] = ck

    try:
        resp = requests.get(
            SPX_GET_ORDER_INFO,
            params=params,
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return None, f"Lỗi kết nối: {exc}"

    try:
        data = resp.json()
    except ValueError:
        return None, f"Không parse JSON (HTTP {resp.status_code}): {resp.text[:500]}"

    if resp.status_code >= 400:
        return data, f"HTTP {resp.status_code}"

    return data, None


def _format_ts_vn(ts: Any) -> str:
    """⏰ 20h:04 19/03/2026"""
    if ts is None:
        return "—"
    try:
        t = int(ts)
    except (TypeError, ValueError):
        return str(ts)
    dt = datetime.fromtimestamp(t, tz=_TZ_VN)
    return f"{dt.hour}h:{dt.minute:02d} {dt.day:02d}/{dt.month:02d}/{dt.year}"


def _format_location_line(loc: Optional[Dict[str, Any]]) -> str:
    if not isinstance(loc, dict):
        return ""
    name = (loc.get("location_name") or "").strip()
    addr = (loc.get("full_address") or "").strip()
    if name and addr:
        return f"{name}: {addr}"
    return name or addr


def _lead_emoji(rec: Dict[str, Any]) -> str:
    """Emoji dòng trạng thái chính (theo tracking_code / milestone)."""
    code = (rec.get("tracking_code") or "").upper()
    tname = (rec.get("tracking_name") or "").lower()
    if code == "F980" or "delivered" in tname:
        return "✅"
    if code == "F600" or "out for delivery" in tname:
        return "🛵"
    if code in ("F100", "F000", "A000"):
        return "📦"
    return "🚚"


def _status_text_upper(rec: Dict[str, Any]) -> str:
    txt = (rec.get("buyer_description") or rec.get("description") or "").strip()
    return txt.upper()


def _sorted_records_from_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    sls = inner.get("sls_tracking_info") if isinstance(inner.get("sls_tracking_info"), dict) else {}
    records: List[Dict[str, Any]] = sls.get("records") or []
    if not isinstance(records, list):
        records = []

    def _sort_key(r: Dict[str, Any]) -> int:
        try:
            return int(r.get("actual_time") or 0)
        except (TypeError, ValueError):
            return 0

    return sorted(records, key=_sort_key)


def _latest_record(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not records:
        return None

    def _t(r: Dict[str, Any]) -> int:
        try:
            return int(r.get("actual_time") or 0)
        except (TypeError, ValueError):
            return 0

    return max(records, key=_t)


def format_spx_summary_html(data: Dict[str, Any], *, spx_tn: str) -> str:
    """
    Tóm tắt HTML: mã vận đơn, mã nội bộ, trạng thái mới nhất (theo ``actual_time``).
    """
    rc = data.get("retcode")
    if rc is not None and rc != 0:
        msg = data.get("message") or ""
        return f"❌ API retcode={rc} {_html(msg)}".strip()

    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    sls = inner.get("sls_tracking_info") if isinstance(inner.get("sls_tracking_info"), dict) else {}
    sls_tn = (sls.get("sls_tn") or "").strip() or "—"
    receiver = (sls.get("receiver_name") or "").strip()

    records = _sorted_records_from_data(data)
    latest = _latest_record(records)

    title = (
        f"📦 <b>{_html(receiver)}</b>"
        if receiver
        else "📦 <b>SPX Tracking</b>"
    )
    lines: List[str] = [
        title,
        "",
        f"<b>MÃ VẬN ĐƠN:</b> <code>{_html(spx_tn)}</code>",
        f"<b>MÃ TRACKING NỘI BỘ:</b> <code>{_html(sls_tn)}</code>",
        "",
        "📍 <b>TRẠNG THÁI MỚI NHẤT:</b>",
    ]

    if not latest:
        lines.append("(Không có bản ghi tracking)")
        return "\n".join(lines)

    lines.append(f"⏰ {_html(_format_ts_vn(latest.get('actual_time')))}")
    emoji = _lead_emoji(latest)
    st = _status_text_upper(latest)
    if st:
        lines.append(f"{emoji} {_html(st)}")

    cur = latest.get("current_location") if isinstance(latest.get("current_location"), dict) else {}
    cur_s = _format_location_line(cur)
    if cur_s:
        lines.append(f"📍 {_html(cur_s)}")

    nxt = latest.get("next_location") if isinstance(latest.get("next_location"), dict) else {}
    nxt_s = _format_location_line(nxt)
    if nxt_s:
        lines.append(f"➡️ TIẾP THEO: 📍 {_html(nxt_s)}")

    return "\n".join(lines)


def _format_sorted_records(records: List[Dict[str, Any]]) -> str:
    """``records`` đã sắp xếp cũ → mới."""
    lines: List[str] = ["LỊCH SỬ GIAO HÀNG:"]

    if not records:
        lines.append("(Không có bản ghi tracking)")
        return "\n".join(lines)

    for i, rec in enumerate(records):
        if i > 0:
            lines.append(HISTORY_SEP)

        lines.append(f"⏰ {_format_ts_vn(rec.get('actual_time'))}")

        emoji = _lead_emoji(rec)
        st = _status_text_upper(rec)
        if st:
            lines.append(f"{emoji} {st}")

        cur = rec.get("current_location") if isinstance(rec.get("current_location"), dict) else {}
        cur_s = _format_location_line(cur)
        if cur_s:
            lines.append(f"📍 {cur_s}")

        nxt = rec.get("next_location") if isinstance(rec.get("next_location"), dict) else {}
        nxt_s = _format_location_line(nxt)
        if nxt_s:
            lines.append(f"➡️ TIẾP THEO: 📍 {nxt_s}")

    return "\n".join(lines)


def format_spx_delivery_history(
    data: Dict[str, Any],
    *,
    max_chars: Optional[int] = None,
) -> str:
    """
    In lịch sử dạng text (form chuẩn): cũ → mới theo ``actual_time``.

    ``max_chars``: nếu set (vd. cho Telegram), bỏ dần **các mốc cũ nhất**
    cho đến khi đủ ngắn; nếu còn 1 mốc mà vẫn quá dài thì cắt cuối bằng ``…``.
    """
    rc = data.get("retcode")
    if rc is not None and rc != 0:
        msg = data.get("message") or ""
        return f"❌ API retcode={rc} {msg}".strip()

    records = _sorted_records_from_data(data)

    if max_chars is None:
        return _format_sorted_records(records)

    if not records:
        return _format_sorted_records([])

    limit = max(1, min(int(max_chars), TELEGRAM_MAX_MESSAGE_CHARS))
    working = list(records)

    while working:
        text = _format_sorted_records(working)
        if len(text) <= limit:
            return text
        if len(working) <= 1:
            if len(text) > limit:
                return text[: max(1, limit - 1)] + "…"
            return text
        working.pop(0)
