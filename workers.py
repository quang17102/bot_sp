# -*- coding: utf-8 -*-
"""
Worker handlers cho c\u00e1c lo\u1ea1i job kh\u00e1c nhau
"""

import html
import time
from datetime import datetime, timedelta, timezone
from job_queue import Job
from typing import Any, Dict
import email_api
import login
import email_utils
from proxy_storage import get_user_best_proxy
from email_utils import process_mailfree

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


def handle_cvc(job: Job) -> Dict[str, Any]:
    """
    Handler \u0111\u1ec3 x\u1eed l\u00fd command /cvc - gi\u1ea3 l\u1eadp x\u1eed l\u00fd m\u1ea5t 20 gi\u00e2y
    
    D\u1eef li\u1ec7u t\u1eeb context \u0111\u01b0\u1ee3c truy\u1ec1n v\u00e0o job.data khi t\u1ea1o job trong cvc_command
    Worker tr\u1ea3 v\u1ec1 result, v\u00e0 check_job_status s\u1ebd g\u1eedi message cho user
    """
    # L\u1ea5y d\u1eef li\u1ec7u t\u1eeb job.data (\u0111\u01b0\u1ee3c truy\u1ec1n t\u1eeb context trong cvc_command)
    input_data = job.data.get("input")  # L\u1ea5y tham s\u1ed1 \u0111\u1ea7u ti\u00ean t\u1eeb context.args
    args = job.data.get("args", [])  # L\u1ea5y to\u00e0n b\u1ed9 args t\u1eeb context.args
    
    # C\u00f3 th\u1ec3 truy c\u1eadp c\u00e1c th\u00f4ng tin kh\u00e1c t\u1eeb job
    user_id = job.user_id  # User ID t\u1eeb update.message.from_user.id
    chat_id = job.chat_id  # Chat ID t\u1eeb update.message.chat.id
    
    # V\u00ed d\u1ee5: X\u1eed l\u00fd d\u1eef li\u1ec7u \u0111\u1ea7u v\u00e0o
    if input_data:
        # X\u1eed l\u00fd v\u1edbi input_data
        processed_message = f"Hello, b\u1ea1n \u0111\u00e3 g\u1eedi: {input_data}"
    else:
        processed_message = "Hello"
    
    # Gi\u1ea3 l\u1eadp x\u1eed l\u00fd m\u1ea5t 20 gi\u00e2y (blocking operation)
    time.sleep(20)

    # Tr\u1ea3 v\u1ec1 k\u1ebft qu\u1ea3 \u0111\u1ec3 check_job_status g\u1eedi message cho user
    return {
        "status": "success",
        "message": processed_message,
        "user_id": user_id,
        "chat_id": chat_id,
        "input_received": input_data,  # Tr\u1ea3 v\u1ec1 d\u1eef li\u1ec7u \u0111\u00e3 nh\u1eadn
        "all_args": args  # Tr\u1ea3 v\u1ec1 t\u1ea5t c\u1ea3 args
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
        
        def format_copyable(value: str) -> str:
            if not value or value == "None":
                return "None"
            return f"<code>{value}</code>"

        proxy_label = proxy_source or "unknown"
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
            # Cùng dict proxy dùng cho login — truyền tiếp sang collect_orders (checkmvd)
            "proxies": proxies,
            "proxy_source": proxy_label,
        }
    except Exception as e:
        print(f"Error: {e}")
        return {
                    "status": "success",
                    "message": "\u274c: Lấy cookie thất bại vui lòng thử lại",  # Message \u0111\u00e3 format HTML
                    "message_format": "HTML"  # \u0110\u00e1nh d\u1ea5u l\u00e0 HTML format
                }

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
