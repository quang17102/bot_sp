# -*- coding: utf-8 -*-
"""
GHN — API tracking-logs (donhang.ghn.vn) và format lịch sử giao hàng (tương tự style SPX).
"""

from __future__ import annotations

import html as html_lib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

GHN_TRACKING_LOGS_URL = (
    "https://fe-online-gateway.ghn.vn/order-tracking/public-api/client/tracking-logs"
)

_TZ_VN = timezone(timedelta(hours=7))

TELEGRAM_MAX_MESSAGE_CHARS = 4096

HISTORY_SEP = "─ ─ ─ ─ ─ ─ ─ ─ ─ ─"

_DEFAULT_HEADERS = {
    "accept": "application/json",
    "accept-language": "vi,en-US;q=0.9,en;q=0.8",
    "content-type": "application/json",
    "origin": "https://donhang.ghn.vn",
    "referer": "https://donhang.ghn.vn/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    ),
}


def get_ghn_tracking_logs(
    order_code: str,
    *,
    token: str = "",
    timeout: float = 25.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    POST ``{"order_code": "..."}``.
    Header ``token`` tùy chọn (một số môi trường không cần vẫn 200).
    """
    order_code = (order_code or "").strip()
    if not order_code:
        return None, "Thiếu order_code"

    headers = dict(_DEFAULT_HEADERS)
    t = (token or "").strip()
    if t:
        headers["token"] = t

    try:
        resp = requests.post(
            GHN_TRACKING_LOGS_URL,
            headers=headers,
            json={"order_code": order_code},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return None, f"Lỗi kết nối: {exc}"

    try:
        data = resp.json()
    except ValueError:
        return None, f"Không parse JSON (HTTP {resp.status_code}): {resp.text[:500]}"

    if resp.status_code >= 400 and not isinstance(data, dict):
        return None, f"HTTP {resp.status_code}"

    return data, None


def _parse_action_at_vn(s: Any) -> datetime:
    """Parse ISO ``action_at`` → giờ VN."""
    if s is None or s == "":
        return datetime.fromtimestamp(0, tz=_TZ_VN)
    t = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return datetime.fromtimestamp(0, tz=_TZ_VN)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TZ_VN)


def _format_ts_vn(dt: datetime) -> str:
    return f"{dt.hour}h:{dt.minute:02d} {dt.day:02d}/{dt.month:02d}/{dt.year}"


def _ghn_lead_emoji(log: Dict[str, Any]) -> str:
    st = (log.get("status") or "").lower()
    action = (log.get("action_code") or "").upper()
    if st in ("delivered",) or action in ("DELIVERED",):
        return "✅"
    if st in ("delivering",) or "DELIVERY" in action:
        return "🛵"
    if st in ("picked", "ready_to_pick", "picking"):
        return "📦"
    if "fail" in st or "FAIL" in action or "RETURN" == action:
        return "❌"
    return "🚚"


def _sorted_logs(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    logs: List[Dict[str, Any]] = inner.get("tracking_logs") or []
    if not isinstance(logs, list):
        logs = []

    def _key(log: Dict[str, Any]) -> float:
        return _parse_action_at_vn(log.get("action_at")).timestamp()

    return sorted(logs, key=_key)


def _html(s: str) -> str:
    return html_lib.escape(str(s or ""), quote=False)


def _format_logs_text(logs: List[Dict[str, Any]]) -> str:
    lines: List[str] = ["LỊCH SỬ GIAO HÀNG (GHN):"]
    if not logs:
        lines.append("(Không có tracking_logs)")
        return "\n".join(lines)

    for i, log in enumerate(logs):
        if i > 0:
            lines.append(HISTORY_SEP)

        dt = _parse_action_at_vn(log.get("action_at"))
        lines.append(f"⏰ {_format_ts_vn(dt)}")

        emoji = _ghn_lead_emoji(log)
        name = (log.get("status_name") or log.get("status") or "").strip().upper()
        if name:
            lines.append(f"{emoji} {name}")

        reason = (log.get("reason") or "").strip()
        if reason:
            lines.append(f"ℹ️ {reason}")

        loc = log.get("location") if isinstance(log.get("location"), dict) else {}
        addr = (loc.get("address") or "").strip()
        if addr:
            lines.append(f"📍 {addr}")

    return "\n".join(lines)


def format_ghn_delivery_history(
    data: Dict[str, Any],
    *,
    max_chars: Optional[int] = None,
) -> str:
    """
    Text kiểu form SPX: ``LỊCH SỬ GIAO HÀNG:``, mốc cũ → mới theo ``action_at``.

    Nếu ``max_chars`` set: bỏ dần các log cũ nhất (đầu danh sách) cho đến khi đủ ngắn.
    """
    code = data.get("code")
    if code is not None and code != 200:
        msg = data.get("message") or ""
        return f"❌ API code={code} {msg}".strip()

    logs = _sorted_logs(data)
    if max_chars is None:
        return _format_logs_text(logs)

    if not logs:
        return _format_logs_text([])

    limit = max(1, min(int(max_chars), TELEGRAM_MAX_MESSAGE_CHARS))
    working = list(logs)

    while working:
        text = _format_logs_text(working)
        if len(text) <= limit:
            return text
        if len(working) <= 1:
            if len(text) > limit:
                return text[: max(1, limit - 1)] + "…"
            return text
        working.pop(0)

    return _format_logs_text([])


def _latest_log(logs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not logs:
        return None

    def _t(l: Dict[str, Any]) -> float:
        return _parse_action_at_vn(l.get("action_at")).timestamp()

    return max(logs, key=_t)


def format_ghn_summary_html(data: Dict[str, Any], *, order_code: str) -> str:
    """
    Tóm tắt HTML: mã đơn, tracking nội bộ (nếu có), trạng thái mới nhất.
    """
    code = data.get("code")
    if code is not None and code != 200:
        msg = data.get("message") or ""
        return f"❌ API code={code} {_html(msg)}".strip()

    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    oi = inner.get("order_info") if isinstance(inner.get("order_info"), dict) else {}
    client_order_code = (oi.get("client_order_code") or "").strip() or "—"
    to_name = (oi.get("to_name") or "").strip()

    logs = _sorted_logs(data)
    latest = _latest_log(logs)

    title = f"📦 <b>{_html(to_name) if to_name else 'GHN Tracking'}</b>"
    lines: List[str] = [
        title,
        "",
        f"<b>MÃ ĐƠN:</b> <code>{_html(order_code)}</code>",
        f"<b>MÃ TRACKING NỘI BỘ:</b> <code>{_html(client_order_code)}</code>",
        "",
        "📍 <b>TRẠNG THÁI MỚI NHẤT:</b>",
    ]

    if not latest:
        lines.append("(Không có bản ghi tracking_logs)")
        return "\n".join(lines)

    dt = _parse_action_at_vn(latest.get("action_at"))
    lines.append(f"⏰ {_html(_format_ts_vn(dt))}")

    emoji = _ghn_lead_emoji(latest)
    name = (latest.get("status_name") or latest.get("status") or "").strip().upper()
    if name:
        lines.append(f"{emoji} {_html(name)}")

    reason = (latest.get("reason") or "").strip()
    if reason:
        lines.append(f"ℹ️ {_html(reason)}")

    loc = latest.get("location") if isinstance(latest.get("location"), dict) else {}
    addr = (loc.get("address") or "").strip()
    if addr:
        lines.append(f"📍 {_html(addr)}")

    return "\n".join(lines)


def format_ghn_order_one_liner(data: Dict[str, Any]) -> str:
    """Một dòng tóm tắt order_info + mốc mới nhất (để debug)."""
    code = data.get("code")
    if code is not None and code != 200:
        return f"code={code} {data.get('message','')}"

    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    oi = inner.get("order_info") if isinstance(inner.get("order_info"), dict) else {}
    oc = (oi.get("order_code") or "").strip()
    sn = (oi.get("status_name") or "").strip()
    logs = _sorted_logs(data)
    if not logs:
        return f"{oc} | {sn} | không có log"
    last = logs[-1]
    last_t = _format_ts_vn(_parse_action_at_vn(last.get("action_at")))
    last_s = (last.get("status_name") or "").strip()
    return f"{oc} | {sn} | mới nhất: {last_t} — {last_s}"
