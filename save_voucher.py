# -*- coding: utf-8 -*-
"""
POST https://mall.shopee.vn/api/v4/microsite/save_voucher

- Session mặc định: ``save_voucher()`` (hằng số đầu file).
- Session động: ``save_voucher_batch(..., cookie_header=..., proxies=...)`` (lệnh ``/vc``).
"""

from __future__ import annotations
import requests
import html
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

SAVE_VOUCHER_URL = "https://mall.shopee.vn/api/v4/microsite/save_voucher"

# --- Voucher mặc định (save_voucher không tham số) ---
VOUCHER_PROMOTIONID = 1364961121046528
VOUCHER_CODE = "CRM19032503NBCP80K"
SIGNATURE = "3e4dc9053e0511d842d8faca0f42ec2b8c9afa204ac5aa91848478216260a050"
CALLER_SOURCE = 6
SIGNATURE_SOURCE = "0"
SECURITY_DEVICE_FINGERPRINT = ""

# --- Session mặc định (capture app) ---
HARDCODED_COOKIE = (
    "SPC_ST=Q2RQTjM5Z3JldzdPa0gwerqbqxccdwx1wlkgcdxILAx7je0T6XfULYgPqYFEMKXUfyqjoiHg5fFtbDZEXajyaoQSO7zpM6f50sUkdMjzKaRdOQUuYL1pv2nQLAqJdmDjARGy8E1HF78vUXm7nAMlsBavhs8gSXbJ4otyYPcqNVECI3yI9R2cm12ij8bpzzSRl5lQQqli1V9XtHsSIo047zYq/NB5wZ1acDl67NGjnRQ=.ALZ+/lNWm32VJxVyXUaojhkw+62hM6pRuaJ39dF0OP5x; "
    # "SPC_U=5947745393; "
    # "SPC_R_T_ID=dFte6KaihQPyQEd/6Fz7zK67FTmzfNOAbeVWZiiiSysdXfqzCVNJbgzrZ/VIDWIziQ/d7hYnv5W9emZ0XvZGkSyP7d1XJV7jGKygOAFifpGg3Wpf3HIbfBUK+GuAX7/9UYxOd9cFHsKatrciI6Z14Dtz1DE8d7lUqeGpFUHTAwQ=; "
    "csrftoken=FL0f7uacukzBCZ6jeC8MwfCSHEXyCjya"
)

HARDCODED_CSRFTOKEN = "FL0f7uacukzBCZ6jeC8MwfCSHEXyCjya"
HARDCODED_X_SAP_RI = "65efc16903d59875cbd64912018d34fbbde0f7984a302aa2770b"

EXTRA_HEADERS: Dict[str, str] = {
    "2e8ec5da": "NMw7ZtDnBLMxod/5zCuiXahCaKy=",
    "55f0c207": "qxMHP7YAsaagPwWUAqPtX2x2+ks=",
    "623b6075": "i3hwLRUty/05iTn07yX4LxbpLob=",
}

ERROR_CODES_AS_OK: Set[int] = frozenset({5})


def build_payload_for(
    voucher_promotionid: Union[int, str],
    voucher_code: str,
    signature: str,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "voucher_promotionid": int(str(voucher_promotionid).strip()),
        "signature": str(signature).strip(),
        "voucher_code": str(voucher_code).strip(),
        "caller_source": CALLER_SOURCE,
        "signature_source": SIGNATURE_SOURCE,
    }
    fp = (SECURITY_DEVICE_FINGERPRINT or "").strip()
    if fp:
        body["security_device_fingerprint"] = fp
    return body


def build_payload() -> Dict[str, Any]:
    return build_payload_for(VOUCHER_PROMOTIONID, VOUCHER_CODE, SIGNATURE)


def build_headers(
    *,
    cookie_header: Optional[str] = None,
    csrftoken: Optional[str] = None,
) -> Dict[str, str]:
    """
    ``cookie_header`` / ``csrftoken`` = None → dùng session mặc định (HARDCODED).
    ``cookie_header`` có giá trị → session động; ``csrftoken`` None thì không gửi ``x-csrftoken``.
    """
    use_default = cookie_header is None
    cookie = HARDCODED_COOKIE if use_default else (cookie_header + "; csrftoken=" + HARDCODED_CSRFTOKEN)
    h: Dict[str, str] = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "Keep-Alive",
        "Content-Type": "application/json",
        "Host": "mall.shopee.vn",
        "Cache-Control": "no-cache, no-store",
        "User-Agent": (
            "Android app Shopee appver=36324 app_type=1 platform=native_android os_ver=30"
        ),
        "x-api-source": "rn",
        "x-sap-type": "2",
        "x-sap-ri": HARDCODED_X_SAP_RI,
        "X-Shopee-Client-Timezone": "Asia/Ho_Chi_Minh",
        "x-shopee-language": "vi",
        "referer": "https://mall.shopee.vn",
        "go-back-step": "1",
        "SHOPEE_HTTP_DNS_MODE": "1",
        "Cookie": cookie,
        "x-csrftoken" : HARDCODED_CSRFTOKEN
    }
    # if use_default:
    #     h["x-csrftoken"] = HARDCODED_CSRFTOKEN
    # elif csrftoken:
    #     h["x-csrftoken"] = csrftoken.strip()
    fp = (SECURITY_DEVICE_FINGERPRINT or "").strip()
    if fp:
        h["af-ac-enc-sz-token"] = fp
    return h


def _post_save_voucher_json(
    body: Dict[str, Any],
    *,
    cookie_header: Optional[str] = None,
    csrftoken: Optional[str] = None,
    timeout: float = 25.0,
    proxies: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    req_kw: Dict[str, Any] = {
        "url": SAVE_VOUCHER_URL,
        "headers": build_headers(cookie_header=cookie_header, csrftoken=csrftoken),
        "json": body,
        "timeout": timeout,
    }
    if proxies:
        req_kw["proxies"] = proxies

    try:
        resp = requests.post(**req_kw)
    except requests.RequestException as exc:
        return None, f"Lỗi kết nối: {exc}"

    try:
        data = resp.json()
    except ValueError:
        snippet = (resp.text or "")[:500].replace("\n", " ")
        return (
            None,
            f"Response không phải JSON (HTTP {resp.status_code}). "
            f"Có thể cookie hết hạn / bị chặn (403 HTML). Body: {snippet!r}",
        )

    if resp.status_code >= 400:
        return data, f"HTTP {resp.status_code}"

    if isinstance(data, dict):
        api_err = data.get("error")
        if api_err not in (None, 0):
            msg = data.get("error_msg") or f"API error={api_err}"
            return data, str(msg)

    return data, None


def save_voucher(
    timeout: float = 25.0,
    proxies: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Lưu một voucher — session mặc định trong file."""
    return _post_save_voucher_json(
        build_payload(), timeout=timeout, proxies=proxies
    )


def save_voucher_item(
    promotionid: Union[int, str],
    voucher_code: str,
    signature: str,
    *,
    cookie_header: Optional[str] = None,
    csrftoken: Optional[str] = None,
    timeout: float = 25.0,
    proxies: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Lưu một voucher; session động khi truyền ``cookie_header``."""
    body = build_payload_for(promotionid, voucher_code, signature)
    return _post_save_voucher_json(
        body,
        cookie_header=cookie_header,
        csrftoken=csrftoken,
        timeout=timeout,
        proxies=proxies,
    )


def classify_line_status(
    data: Optional[Dict[str, Any]],
    err: Optional[str],
    *,
    error_codes_as_ok: Set[int] = ERROR_CODES_AS_OK,
) -> Tuple[str, str]:
    if err is None:
        return "OK", "Đã lưu thành công."

    if data is None:
        return "Lỗi", err

    code = data.get("error")
    if isinstance(code, int) and code in error_codes_as_ok:
        msg = (data.get("error_msg") or err or "").strip() or err
        return "OK", msg

    msg = (data.get("error_msg") or err or "").strip() or err
    return "Lỗi", msg


def _item_ten_ma(item: Dict[str, Any]) -> str:
    name = (item.get("ten_ma") or "").strip()
    if name:
        return name
    vc = (item.get("voucher_code") or "").strip()
    if vc:
        return vc
    return str(item.get("promotionid", "?"))


def save_voucher_batch(
    items: Sequence[Dict[str, Any]],
    *,
    cookie_header: Optional[str] = None,
    csrftoken: Optional[str] = None,
    timeout: float = 25.0,
    proxies: Optional[Dict[str, str]] = None,
    error_codes_as_ok: Set[int] = ERROR_CODES_AS_OK,
) -> List[Dict[str, Any]]:
    """
    Lưu lần lượt từng phần tử. Luôn truyền ``proxies`` khi gọi từ bot (cùng proxy lấy SPC_ST).

    Trả về list dict gồm ``ten_ma``, ``voucher_code``, ``status``, ``message``, ``data``, ``err``.
    """
    out: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        pid = raw.get("promotionid")
        vc = raw.get("voucher_code")
        sig = raw.get("signature")
        label = _item_ten_ma(raw)
        vcode_str = str(vc).strip() if vc is not None else ""
        if pid is None or vc is None or sig is None:
            out.append(
                {
                    "ten_ma": label,
                    "voucher_code": vcode_str or "?",
                    "status": "Lỗi",
                    "message": "Thiếu promotionid / voucher_code / signature",
                    "data": None,
                    "err": "invalid_item",
                }
            )
            continue

        data, err = save_voucher_item(
            pid,
            vcode_str,
            str(sig).strip(),
            cookie_header=cookie_header,
            csrftoken=csrftoken,
            timeout=timeout,
            proxies=proxies,
        )
        status, message = classify_line_status(
            data, err, error_codes_as_ok=error_codes_as_ok
        )
        out.append(
            {
                "ten_ma": label,
                "voucher_code": vcode_str,
                "status": status,
                "message": message,
                "data": data,
                "err": err,
            }
        )
    return out


def format_save_voucher_report_lines(results: Sequence[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for r in results:
        name = (r.get("ten_ma") or "").strip() or "?"
        st = (r.get("status") or "Lỗi").strip()
        msg = (r.get("message") or "").strip()
        blocks.append(f"{name}\n{st} : {msg}")
    return "\n\n".join(blocks)


def format_vc_telegram_html(results: Sequence[Dict[str, Any]]) -> str:
    """
    Phần thân báo cáo (sau tiêu đề): mỗi voucher ``----------``, ``✅/❌`` + ``voucher_code``, ``→ OK`` hoặc ``→ Lỗi: ...``.
    """
    parts: List[str] = []
    for r in results:
        vc = (r.get("voucher_code") or "").strip() or "?"
        st = (r.get("status") or "Lỗi").strip()
        msg = (r.get("message") or "").strip()
        vc_esc = html.escape(vc)
        sep = "----------"
        if st == "OK":
            parts.append(f"{sep}\n✅ <code>{vc_esc}</code>\n→ OK")
        else:
            parts.append(
                f"{sep}\n❌ <code>{vc_esc}</code>\n→ Lỗi: {html.escape(msg)}"
            )
    return "\n\n".join(parts)


def print_save_voucher_report(
    items: Sequence[Dict[str, Any]],
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    results = save_voucher_batch(items, **kwargs)
    print(format_save_voucher_report_lines(results))
    return results
