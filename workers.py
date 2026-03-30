# -*- coding: utf-8 -*-
"""
Worker handlers cho c\u00e1c lo\u1ea1i job kh\u00e1c nhau
"""

import html
import os
import time
from datetime import datetime, timedelta, timezone
from job_queue import Job
from typing import Any, Dict
from mail import api as email_api
from mail import utils as email_utils
from mail.utils import process_mailfree
import login
import login_qr
import voucher_status
from voucher_status import (
    VOUCHER_BATCH_LIST_HARDCODED,
    fetch_voucher_batch_parallel,
    format_batch_cards_telegram_html,
)
from proxy_storage import get_user_best_proxy

# Giờ Việt Nam (UTC+7, không DST)
_TZ_VN = timezone(timedelta(hours=7))

def _format_created_display(created_raw: Any) -> str:
    """
    Đưa created từ API (ISO UTC, epoch, hoặc chuỗi) về dạng: dd/mm/yyyy HH:mm:ss (theo giờ VN).
    Ví dụ: 04/03/2026 06:38:34
    """
    if created_raw is None:
        return "None"
    s = str(created_raw).strip()
    if not s or s.lower() == "none":
        return "None"
    try:
        # ISO 8601 (vd. 2026-03-04T06:38:34+00:00 hoặc ...Z)
        if "T" in s or (len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                # Coi naive là UTC (thường gặp từ API)
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(_TZ_VN).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        pass
    try:
        # "2026-03-04 06:38:34" (không có timezone)
        if len(s) >= 19 and s[4:5] == "-" and s[7:8] == "-" and s[10:11] in " T":
            dt = datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(_TZ_VN).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        pass
    try:
        # Unix seconds / milliseconds
        num = float(s)
        if num > 1e12:
            num = num / 1000.0
        dt = datetime.fromtimestamp(num, tz=timezone.utc).astimezone(_TZ_VN)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        pass
    return s


def _format_cks_success_from_user_info(
    user_info: dict,
    proxies: dict,
    proxy_label: str,
) -> Dict[str, Any]:
    """Payload giống handle_cks khi đã có user_info + proxy."""

    def format_copyable(value: str) -> str:
        if not value or value == "None":
            return "None"
        return f"<code>{value}</code>"

    cookie_text = f"SPC_ST={user_info['spc_st']}"
    message_html = (
        "✅ Nhấn vô Cookies để COPY\n\n"
        f"<code>{cookie_text}</code>\n\n"
        "<b>📋 Thông Tin Tài Khoản:</b>\n"
        f"• Username: {format_copyable(user_info['username'])}\n"
        f"• Email: {format_copyable(user_info['email'])}\n"
        f"• Phone: {format_copyable(user_info['phone'])}\n"
        f"• Ngày tạo: {format_copyable(_format_created_display(user_info.get('created')))}"
    )
    return {
        "status": "success",
        "message": message_html,
        "message_format": "HTML",
        "store_creds": cookie_text,
        "proxies": proxies,
        "proxy_source": proxy_label,
    }


def handle_cvc(job: Job) -> Dict[str, Any]:
    """
    Handler cho /cvc — gọi API voucher mall (đa luồng) với danh sách hardcode
    ``VOUCHER_BATCH_LIST_HARDCODED`` trong ``voucher_status.py``, hiển thị thẻ voucher (HTML).
    Cookie mall: biến môi trường ``SHOPEE_MALL_COOKIE`` (có thể rỗng).
    **Không dùng proxy** — luôn gọi trực tiếp (check voucher).
    """
    user_id = job.user_id
    chat_id = job.chat_id
    input_data = job.data.get("input")
    args = job.data.get("args", [])

    try:
        cookie = os.getenv("SHOPEE_MALL_COOKIE", "").strip()
        items = list(VOUCHER_BATCH_LIST_HARDCODED)
        if not items:
            return {
                "status": "success",
                "message": "❌ <b>VOUCHER_BATCH_LIST_HARDCODED</b> đang rỗng — thêm voucher trong <code>voucher_status.py</code>.",
                "message_format": "HTML",
            }

        n = len(items)
        workers = min(voucher_status.DEFAULT_BATCH_WORKERS, max(1, n))
        rows = fetch_voucher_batch_parallel(
            items,
            cookie=cookie,
            max_workers=workers,
            proxies=None,
        )
        msg = format_batch_cards_telegram_html(rows)
        return {
            "status": "success",
            "message": msg,
            "message_format": "HTML",
            "user_id": user_id,
            "chat_id": chat_id,
            "input_received": input_data,
            "all_args": args,
        }
    except Exception as e:
        print(f"Error handle_cvc: {e}")
        return {
            "status": "success",
            "message": f"❌ Lỗi /cvc: {html.escape(str(e))}",
            "message_format": "HTML",
            "user_id": user_id,
            "chat_id": chat_id,
            "input_received": input_data,
            "all_args": args,
        }

def handle_cks(job: Job) -> Dict[str, Any]:
    input_data = job.data.get("input")  # L\u1ea5y tham s\u1ed1 \u0111\u1ea7u ti\u00ean t\u1eeb context.args
    args = job.data.get("args", [])  # L\u1ea5y to\u00e0n b\u1ed9 args t\u1eeb context.args
    user_id = job.user_id  # User ID t\u1eeb update.message.from_user.id
    chat_id = job.chat_id  # Chat ID t\u1eeb update.message.chat.id
    
    if not input_data:
        return {
            "status": "error",
            "error": "Thi\u1ebfu input data"
        }
    
    try:
        # Lấy proxy tốt nhất cho user (kiot ưu tiên, sau đó tới vnpx)
        proxies, proxy_source = get_user_best_proxy(user_id)
        if proxies is None or proxies == {}:
            return {
                "status": "success",
                "message": "❌ Vui lòng kiểm tra proxy nhé!!!",
                "message_format": "HTML",
            }
        # Extract SPC_ST từ input (dùng proxy nếu có)
        user_info = login.extract_spc_st_and_user_info(input_data, proxies=proxies, device_id="123")
        if isinstance(user_info, str):
            return {
                "status": "success",
                "message": user_info,
                "message_format": "HTML",
            }
        if not isinstance(user_info, dict) or not user_info.get("spc_st"):
            return {
                "status": "success",
                "message": "❌: Lấy cookie thất bại vui lòng thử lại",
                "message_format": "HTML",
            }

        proxy_label = proxy_source or "unknown"
        return _format_cks_success_from_user_info(user_info, proxies, proxy_label)
    except Exception as e:
        print(f"Error: {e}")
        return {
                    "status": "success",
                    "message": "\u274c: Lấy cookie thất bại vui lòng thử lại",  # Message \u0111\u00e3 format HTML
                    "message_format": "HTML"  # \u0110\u00e1nh d\u1ea5u l\u00e0 HTML format
                }


def handle_qr(job: Job) -> Dict[str, Any]:
    """
    Poll get_qr_status theo qrcode_id; khi CONFIRMED thì login_with_qr
    và trả về cùng format handle_cks (cookie + thông tin + proxies cho collect_orders).
    """
    qrcode_id = (job.data or {}).get("qrcode_id")
    if not qrcode_id:
        return {
            "status": "success",
            "message": "❌ Thiếu qrcode_id (lỗi dữ liệu job).",
            "message_format": "HTML",
        }
    user_id = job.user_id
    poll_interval = 2
    max_wait = 180
    started = time.time()

    while True:
        if time.time() - started > max_wait:
            return {
                "status": "success",
                "message": "❌ Hết thời gian chờ quét QR (3 phút).",
                "message_format": "HTML",
            }

        status_result = login_qr.get_qr_status(qrcode_id)
        if status_result.get("status") != "success":
            err = status_result.get("message", "unknown")
            return {
                "status": "success",
                "message": f"❌ Lỗi kiểm tra QR: {html.escape(str(err))}",
                "message_format": "HTML",
            }

        data = status_result.get("data") or {}
        qr_status = (data.get("status") or "").upper()
        qrcode_token = data.get("qrcode_token", "")

        if qr_status == "CONFIRMED":
            if not qrcode_token:
                return {
                    "status": "success",
                    "message": "❌ QR đã xác nhận nhưng thiếu token.",
                    "message_format": "HTML",
                }
            login_result = login_qr.login_with_qr(qrcode_token)
            if login_result.get("status") != "success":
                msg = login_result.get("message", "Đăng nhập QR thất bại")
                return {
                    "status": "success",
                    "message": f"❌ {html.escape(str(msg))}",
                    "message_format": "HTML",
                }
            cookies = login_result.get("cookies") or {}
            spc_st = cookies.get("SPC_ST")
            if not spc_st:
                return {
                    "status": "success",
                    "message": "❌ Không lấy được SPC_ST sau đăng nhập QR.",
                    "message_format": "HTML",
                }
            proxies, proxy_source = get_user_best_proxy(user_id)
            if proxies is None or proxies == {}:
                return {
                    "status": "success",
                    "message": "❌ Vui lòng kiểm tra proxy nhé!!!",
                    "message_format": "HTML",
                }
            user_info = login.build_user_info_dict_from_spc_st(
                spc_st, proxies=proxies, device_id="123"
            )
            if not user_info or not user_info.get("spc_st"):
                return {
                    "status": "success",
                    "message": "❌ Không lấy được thông tin tài khoản",
                    "message_format": "HTML",
                }
            proxy_label = proxy_source or "unknown"
            return _format_cks_success_from_user_info(user_info, proxies, proxy_label)

        time.sleep(poll_interval)


def handle_checkmail(job: Job) -> Dict[str, Any]:
    """
    Worker handler cho command /checkmail
    Lấy danh sách email từ TempMail API và format lại
    """
    try:
        # Lấy dữ liệu từ job
        job_data = job.data or {}
        email = job_data.get("email")
        password = job_data.get("password")
        if not email or not password:
            return {
                "status": "error",
                "error": "Thiếu email hoặc password"
            }
        
        # Gọi API để lấy danh sách email
        result = email_utils.get_emails_from_tempmail(email, password)
        print(f"result:{result}")
        if result["status"] == "error":
                return {
                "status": "success",
                "message": "❌ Opps!!! Email die rùi!!!",
                "message_format": "HTML",
            }
        
        emails = result.get("emails", [])
        
        if not emails:
            return {
                "status": "success",
                "message": "📭 Không có email nào trong hộp thư.",
                "message_format": "HTML",
                "inline_keyboard": [
                    [
                        {"text": "📩 Đọc email", "callback_data": f"email_read_{job.job_id}"},
                        {"text": "ℹ️ Thông tin email", "callback_data": f"email_info_{job.job_id}"},
                    ],
                ],
            }
        
        # Format danh sách email
        message = email_utils.format_emails_list(emails)
        
        return {
            "status": "success",
            "message": message,
            "message_format": "HTML",
            "emails": emails,  # Lưu emails để có thể truy xuất khi click button
            "has_buttons": True  # Đánh dấu có buttons
        }
        
    except Exception as e:
        print(f"Error in handle_checkmail: {e}")
        return {
            "status": "success",
            "message": "❌ Opps!!! Email die rùi!!!",
            "message_format": "HTML",
        }

def handle_mailfree(job: Job) -> Dict[str, Any]:
    """
    Worker handler cho command /mailfree.
    Input hỗ trợ 2 dạng:
      1) SPC_ST=... (cookie) -> register_email_full để lấy email+password, sau đó add email.
      2) id|pass|spc_f -> extract SPC_ST, sau đó add email.
    """
    user_id = job.user_id
    job_data = job.data or {}
    

    raw = ""
    if isinstance(job_data, dict):
        raw = str(job_data.get("input") or "").strip()
    else:
        raw = str(job_data).strip()

    if not raw:
        return {"status": "success", "message": "❌ Thiếu input!!!"}
    try:
        proxies, proxy_source = get_user_best_proxy(user_id)
        print(f"proxies:{proxies}")
        print(f"proxy_source:{proxy_source}")
        if proxies == None or proxies == {}:
            return {
                "status": "success",
                "message": "❌ Vui lòng kiểm tra proxy nhé!!!",
                "message_format": "HTML",
            }
        print(proxies)
        result = process_mailfree(raw_input=raw, proxies=proxies)

        # Nếu tạo email thành công thì thêm nút "Đọc email" (chuyển qua UI checkmail)
        email = (result.get("email") or "").strip()
        password = (result.get("password") or "").strip()
        if email and password:
            result["store_creds"] = {"email": email, "password": password}
            result["inline_keyboard"] = [
                [{"text": "📩 Đọc email", "callback_data": f"email_read_{job.job_id}"}]
            ]

        return result
    except Exception as e:
        print(f"Error in handle_mailfree: {e}")
        return {
            "status": "success",
            "message": "❌ Không add được email free vui lòng thử lại!!!",
            "message_format": "HTML",
        }


def handle_addmail(job: Job) -> Dict[str, Any]:
    """
    Worker handler cho command /addmail.

    Input (từ commands.py):
      - "input": id|pass|cookie_f
      - "email": email cần add vào Shopee account

    Luồng:
      1) Tạo SPC_ST từ login.extract_spc_st (dựa trên id/pass/cookie_f)
      2) Gọi api_add_email_by_cookie(cookie=SPC_ST, email=...) để add email
    """
    user_id = job.user_id
    job_data = job.data or {}

    raw = ""
    if isinstance(job_data, dict):
        raw = str(job_data.get("input") or "").strip()
    else:
        raw = str(job_data).strip()

    email = ""
    if isinstance(job_data, dict):
        email = str(job_data.get("email") or "").strip()

    if not raw or not email:
        return {
            "status": "success",
            "message": "❌ Thiếu input hoặc email!!!",
            "message_format": "HTML",
        }

    try:
        proxies, proxy_source = get_user_best_proxy(user_id)
        if proxies is None or proxies == {}:
            return {
                "status": "success",
                "message": "❌ Vui lòng kiểm tra proxy nhé!!!",
                "message_format": "HTML",
            }

        parts = [p.strip() for p in raw.split("|")]
        # Cho phép 2 dạng:
        #   1) id|pass|cookie_f
        #   2) id|pass|sdt|cookie_f (sdt có thể bỏ qua/rỗng)
        if len(parts) not in (3, 4):
            return {
                "status": "success",
                "message": "❌ Format input sai! Dùng: <code>id|pass|cookie_f</code> hoặc <code>id|pass|sdt|cookie_f</code>",
                "message_format": "HTML",
            }
        spc_user = parts[0] if len(parts) >= 1 else ""
        spc_pass = parts[1] if len(parts) >= 2 else ""
        cookie_f = parts[2] if len(parts) == 3 else parts[3]
        sdt = "" if len(parts) == 3 else parts[2]

        if not spc_user or not spc_pass or not cookie_f:
            return {
                "status": "success",
                "message": "❌ Input không được để trống! Dùng: <code>id|pass|cookie_f</code> hoặc <code>id|pass|sdt|cookie_f</code>",
                "message_format": "HTML",
            }

        # login.parse_input() cần 4 phần: username|password|sdt|SPC_F (sdt có thể rỗng)
        # - nếu user không truyền sdt -> dùng chuỗi rỗng
        input_line = f"{spc_user}|{spc_pass}|{sdt}|{cookie_f}"
        spc_st = login.extract_spc_st(input_line, proxies=proxies)

        add_result = email_utils.api_add_email_by_cookie(
            cookie=spc_st,
            email=email,
            proxies=proxies,
        )

        success = bool(add_result.get("success"))
        username = add_result.get("username") or "—"
        phone = add_result.get("phone") or "—"
        raw_message = add_result.get("message") or ""

        if success:
            msg = (
                "✅ <b>Thêm email thành công</b>\n\n"
                f"📧 Email: <code>{html.escape(email)}</code>\n"
                f"👤 Username: <code>{html.escape(str(username))}</code>\n"
                f"📱 Phone: <code>{html.escape(str(phone))}</code>\n"
            )
            return {
                "status": "success",
                "message": msg,
                "message_format": "HTML",
            }

        msg = (
            "❌ <b>Thêm email thất bại</b>\n\n"
            f"📧 Email: <code>{html.escape(email)}</code>\n"
        )
        if raw_message:
            msg += f"\n\n⚠️ {html.escape(str(raw_message))}"
        else:
            msg += "\n\n⚠️ Không xác định được lỗi."
        if username != "—" or phone != "—":
            msg += (
                f"\n\n👤 Username: <code>{html.escape(str(username))}</code>"
                f"\n📱 Phone: <code>{html.escape(str(phone))}</code>"
            )

        return {
            "status": "success",
            "message": msg,
            "message_format": "HTML",
        }
    except Exception as e:
        return {
            "status": "success",
            "message": f"❌ Không add được email. Lỗi: <code>{html.escape(str(e))}</code>",
            "message_format": "HTML",
        }


def handle_newmail(job: Job) -> Dict[str, Any]:
    """
    /newmail — chỉ gọi register_email_full (email + password random), không gắn Shopee.
    Không dùng proxy (gọi API trực tiếp như email_api).
    Trả về nút Đọc email + Thông tin email (cùng callback với checkmail/mailfree).
    """
    try:
        email, password, reg_result = email_api.register_email_full("", "", proxies=None)
        if not email or not password:
            if isinstance(reg_result, dict):
                err_raw = reg_result.get("message") or reg_result.get("error") or str(reg_result)
            else:
                err_raw = str(reg_result)
            err_hint = html.escape(str(err_raw)[:400])
            return {
                "status": "success",
                "message": f"❌ Không tạo được email.\n<code>{err_hint}</code>",
                "message_format": "HTML",
            }
        msg = (
            "✅ <b>Đã tạo email mới</b>\n\n"
            f"📧 Email: <code>{html.escape(email)}</code>\n"
            f"🔑 Password: <code>{html.escape(password)}</code>\n"
            f"📋 Copy: <code>{html.escape(email)}|{html.escape(password)}</code>\n"
        )
        return {
            "status": "success",
            "message": msg,
            "message_format": "HTML",
            "store_creds": {"email": email, "password": password},
            "inline_keyboard": [
                [
                    {"text": "📩 Đọc email", "callback_data": f"email_read_{job.job_id}"},
                    {"text": "ℹ️ Thông tin email", "callback_data": f"email_info_{job.job_id}"},
                ],
            ],
        }
    except Exception as e:
        print(f"Error in handle_newmail: {e}")
        return {
            "status": "success",
            "message": "❌ Lỗi khi tạo email. Vui lòng thử lại!",
            "message_format": "HTML",
        }
