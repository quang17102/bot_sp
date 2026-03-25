# -*- coding: utf-8 -*-
"""
Command handlers cho Telegram Bot
T\u1EA5t c\u1EA3 c\u00E1c command handlers \u0111\u01B0\u1EE3c \u0111\u1ECBnh ngh\u0129a \u1EDF \u0111\u00E2y
"""
import base64
import html
import io
import re
from shipping import spx, ghn
import checkmvd
import asyncio
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from job_queue import JobQueue
from typing import TYPE_CHECKING, Optional
from mail import utils as email_utils
from mail.verify import verify_link
from proxy_storage import (
    save_user_proxy_key,
    get_user_proxy_key,
    delete_user_proxies,
    get_user_best_proxy,
)
import login
import login_qr

if TYPE_CHECKING:
    from telegram.ext import Application

# Module-level cache để lưu emails theo job_id
# Format: {job_id: [emails_list]}
_email_cache: dict[str, list] = {}
# Lưu credential để refresh inbox theo job_id
# Format: {job_id: {"email": "...", "password": "..."}}
_email_creds: dict[str, dict[str, str]] = {}


def _empty_inbox_reply_markup(job_id: str) -> InlineKeyboardMarkup:
    """Khi hộp thư trống: vẫn cho đọc lại inbox + xem thông tin đăng nhập."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="📩 Đọc email",
                    callback_data=f"email_read_{job_id}",
                ),
                InlineKeyboardButton(
                    text="ℹ️ Thông tin email",
                    callback_data=f"email_info_{job_id}",
                ),
            ]
        ]
    )


def _escape(v) -> str:
    return html.escape(str(v or ""))


def _copyable(v) -> str:
    """Giá trị bọc <code> để người dùng dễ chạm copy trên Telegram (parse_mode HTML)."""
    return f"<code>{_escape(v)}</code>"


def _mask_shopee_account(account: Optional[str]) -> str:
    """Ẩn phần giữa tài khoản (vd. 1***q9j)."""
    if not account:
        return "—"
    s = str(account).strip()
    if not s:
        return "—"
    if len(s) <= 4:
        return f"{s[0]}***"
    return f"{s[0]}***{s[-3:]}"


def _login_warning_time_display(email: dict) -> str:
    """Ưu tiên Thời gian truy cập trong body; không có thì format date mail theo giờ VN."""
    body = email.get("body_text") or ""
    time_access = email_utils.parse_time_from_body(body)
    if time_access:
        return time_access.strip()
    ts = email.get("date") or ""
    if not ts:
        return "—"
    try:
        date_str = ts
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        elif "+" not in date_str[-6:] and "-" not in date_str[-6:]:
            date_str = date_str + "+00:00"
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        vn = timezone(timedelta(hours=7))
        return dt.astimezone(vn).strftime("%d/%m/%Y %H:%M")
    except Exception:
        out = email_utils.format_timestamp_for_email(ts)
        return out if out else "—"


def format_order_like_form(order: dict) -> str:
    order_id = order.get("order_id", "")
    status = order.get("status", "") or ""
    order_time = order.get("order_time", "")
    shipping_name = order.get("shipping_name", "")
    shipping_phone = order.get("shipping_phone", "")
    shipping_address = order.get("shipping_address", "")
    name = order.get("name", "") or "Khong co ten"
    model_name = order.get("model_name") or ""
    tracking = order.get("tracking_number") or "Khong co ma van don"
    logistics = order.get("logistics") or {}
    carrier = logistics.get("carrier_name") or ""
    # Chọn “trạng thái mô tả” kiểu form: ưu tiên history, fallback status
    history = logistics.get("history") or []
    status_text = status
    if isinstance(history, list) and history:
        # dùng mô tả sự kiện cuối cùng (thường là trạng thái mới nhất)
        last = history[-1] or {}
        desc = last.get("description") or ""
        if desc:
            status_text = desc
    total_money = checkmvd.format_money_for_total(order.get("final_total"))
    # Nếu trạng thái bị hủy -> có dòng đỏ "Hủy đơn" (so khớp sau khi bỏ dấu — trạng thái có thể là tiếng Việt có dấu)
    s_fold = checkmvd.fold_vietnamese(str(status_text).lower())
    is_cancel = (
        ("huy" in s_fold)
        or ("hoan tra" in s_fold)
        or ("hoan tien" in s_fold)
        or ("da huy" in s_fold)
    )
    # Build UI text giống form — các trường quan trọng bọc <code> để copy nhanh
    lines = []
    lines.append(f"🧾 <b>Đơn #{_escape(order_id)}</b>")
    # if order_time:
    #     lines.append(f"🕒 <b>Thời gian:</b> {_escape(order_time)}")
    lines.append(f"\n👤 <b>Người nhận:</b> {_copyable(shipping_name)}")
    lines.append(f"📞 <b>SDT:</b> {_copyable(shipping_phone)}")
    lines.append(f"🏠 <b>Địa chỉ:</b> {_copyable(shipping_address)}")
    if carrier:
        lines.append(f"\n🚚 <b>Mã vận đơn:</b> {_copyable(tracking)} ({_escape(carrier)})")
    else:
        lines.append(f"\n🚚 <b>Mã vận đơn:</b> {_copyable(tracking)}")
    lines.append(f"\n📦 <b>Sản phẩm:</b> {_copyable(name)}")
    if model_name:
        lines.append(f"  <b>Phân loại:</b> {_copyable(model_name)}")
    lines.append(f"\n💰 <b>Tổng cộng:</b> {_escape(total_money)} đ")
    lines.append(f"\n🔎 <b>Trạng thái:</b> {_escape(status_text)}")
    if is_cancel:
        lines.append("\n❌ <b>Hủy đơn</b>")
    return "\n".join(lines)

async def cvc_command(update: Update, context: ContextTypes.DEFAULT_TYPE, job_queue: JobQueue, bot_app: 'Application'):
    """Handler cho command /cvc"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    # L\u1EA5y d\u1EEF li\u1EC7u t\u1EEB context
    # 1. L\u1EA5y arguments sau command (v\u00ED d\u1EE5: /cvc arg1 arg2)
    args = context.args  # List c\u00E1c tham s\u1ED1, v\u00ED d\u1EE5: ['arg1', 'arg2']
    
    # 2. L\u1EA5y bot_data (d\u1EEF li\u1EC7u chung cho bot)
    bot_data = context.bot_data  # Dict \u0111\u1EC3 l\u01B0u d\u1EEF li\u1EC7u chung
    
    # 3. L\u1EA5y user_data (d\u1EEF li\u1EC7u ri\u00EAng cho t\u1EEBng user)
    user_data = context.user_data  # Dict \u0111\u1EC3 l\u01B0u d\u1EEF li\u1EC7u theo user_id
    
    # 4. L\u1EA5y chat_data (d\u1EEF li\u1EC7u ri\u00EAng cho t\u1EEBng chat)
    chat_data = context.chat_data  # Dict \u0111\u1EC3 l\u01B0u d\u1EEF li\u1EC7u theo chat_id
    
    # V\u00ED d\u1EE5: L\u1EA5y tham s\u1ED1 \u0111\u1EA7u ti\u00EAn n\u1EBFu c\u00F3
    input_data = args[0] if args and len(args) > 0 else None
    
    # Atomic operation: Check + Create trong c\u00F9ng lock \u0111\u1EC3 tr\u00E1nh race condition
    job_id = job_queue.add_job_if_no_active(
        job_type="cvc",
        user_id=user_id,
        chat_id=chat_id,
        data={
            "input": input_data,  # Truy\u1EC1n d\u1EEF li\u1EC7u t\u1EEB context v\u00E0o job
            "args": args  # Ho\u1EB7c truy\u1EC1n to\u00E0n b\u1ED9 args
        }
    )
    
    # N\u1EBFu job_id l\u00E0 None \u2192 User \u0111\u00E3 c\u00F3 job \u0111ang ch\u1EA1y
    if job_id is None:
        # L\u1EA5y job \u0111ang ch\u1EA1y \u0111\u1EC3 hi\u1EC3n th\u1ECB th\u00F4ng tin
        active_job = job_queue.get_active_job_for_user(user_id, job_type="cvc")
        if active_job:
            status_text = "\u0111ang ch\u1EDD" if active_job.status == "pending" else "\u0111ang x\u1EED l\u00FD"
            await update.message.reply_text(
                f"\u23F8\uFE0F B\u1EA1n \u0111\u00E3 c\u00F3 job \u0111ang {status_text}!\n"
                f"\U0001F4CB Job ID: {active_job.job_id[:8]}\n"
                f"\u23F3 Tr\u1EA1ng th\u00E1i: {active_job.status}\n"
                f"Vui l\u00F2ng \u0111\u1EE3i job hi\u1EC7n t\u1EA1i ho\u00E0n th\u00E0nh tr\u01B0\u1EDBc khi g\u1EEDi request m\u1EDBi."
            )
        else:
            await update.message.reply_text(
                "\u23F8\uFE0F B\u1EA1n \u0111\u00E3 c\u00F3 job \u0111ang x\u1EED l\u00FD. Vui l\u00F2ng \u0111\u1EE3i job hi\u1EC7n t\u1EA1i ho\u00E0n th\u00E0nh."
            )
        return
    
    # Tr\u1EA3 v\u1EC1 ngay l\u1EADp t\u1EE9c (kh\u00F4ng ch\u1EDD x\u1EED l\u00FD)
    processing_msg = await update.message.reply_text(
        "\u23F3 \u0110ang x\u1EED l\u00FD..."
    )
    processing_msg_id = processing_msg.message_id
    
    # B\u1EAFt \u0111\u1EA7u polling \u0111\u1EC3 check job status
    asyncio.create_task(check_job_status(chat_id, job_id, job_queue, bot_app, processing_msg_id))


async def cks_command(update: Update, context: ContextTypes.DEFAULT_TYPE, job_queue: JobQueue, bot_app: 'Application'):
    """Handler cho command /cks"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    # L\u1EA5y d\u1EEF li\u1EC7u t\u1EEB context
    args = context.args  # List c\u00E1c tham s\u1ED1
    
    # L\u1EA5y tham s\u1ED1 \u0111\u1EA7u ti\u00EAn n\u1EBFu c\u00F3
    input_data = args[0] if args and len(args) > 0 else None
    
    # Atomic operation: Check + Create trong c\u00F9ng lock \u0111\u1EC3 tr\u00E1nh race condition
    job_id = job_queue.add_job_if_no_active(
        job_type="cks",
        user_id=user_id,
        chat_id=chat_id,
        data={
            "input": input_data,  # Truy\u1EC1n d\u1EEF li\u1EC7u t\u1EEB context v\u00E0o job
            "args": args  # Ho\u1EB7c truy\u1EC1n to\u00E0n b\u1ED9 args
        }
    )
    
    # N\u1EBFu job_id l\u00E0 None \u2192 User \u0111\u00E3 c\u00F3 job \u0111ang ch\u1EA1y
    if job_id is None:
        # L\u1EA5y job \u0111ang ch\u1EA1y \u0111\u1EC3 hi\u1EC3n th\u1ECB th\u00F4ng tin
        active_job = job_queue.get_active_job_for_user(user_id, job_type="cks")
        if active_job:
            status_text = "\u0111ang ch\u1EDD" if active_job.status == "pending" else "\u0111ang x\u1EED l\u00FD"
            await update.message.reply_text(
                f"\u23F8\uFE0F B\u1EA1n \u0111\u00E3 c\u00F3 job \u0111ang {status_text}!\n"
                f"\U0001F4CB Job ID: {active_job.job_id[:8]}\n"
                f"\u23F3 Tr\u1EA1ng th\u00E1i: {active_job.status}\n"
                f"Vui l\u00F2ng \u0111\u1EE3i job hi\u1EC7n t\u1EA1i ho\u00E0n th\u00E0nh tr\u01B0\u1EDBc khi g\u1EEDi request m\u1EDBi."
            )
        else:
            await update.message.reply_text(
                "\u23F8\uFE0F B\u1EA1n \u0111\u00E3 c\u00F3 job \u0111ang x\u1EED l\u00FD. Vui l\u00F2ng \u0111\u1EE3i job hi\u1EC7n t\u1EA1i ho\u00E0n th\u00E0nh."
            )
        return
    
    # Tr\u1EA3 v\u1EC1 ngay l\u1EADp t\u1EE9c (kh\u00F4ng ch\u1EDD x\u1EED l\u00FD)
    processing_msg = await update.message.reply_text(
        "\u23F3 \u0110ang x\u1EED l\u00FD..."
    )
    processing_msg_id = processing_msg.message_id
    
    # B\u1EAFt \u0111\u1EA7u polling \u0111\u1EC3 check job status
    asyncio.create_task(check_job_status(chat_id, job_id, job_queue, bot_app, processing_msg_id))


async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE, job_queue: JobQueue, bot_app: 'Application'):
    """Handler cho command /qr — gửi ảnh QR, worker poll đến khi CONFIRMED rồi trả giống /cks."""
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    gen_result = await asyncio.to_thread(login_qr.gen_qr_login)
    if gen_result.get("status") != "success":
        await update.message.reply_text(
            f"❌ {gen_result.get('message', 'Không tạo được mã QR.')}"
        )
        return

    qrcode_base64 = gen_result.get("qrcode_base64")
    qrcode_id = gen_result.get("qrcode_id")
    b64_data = qrcode_base64
    if "," in (qrcode_base64 or "") and (qrcode_base64 or "").startswith("data:image"):
        b64_data = qrcode_base64.split(",", 1)[1]
    try:
        png_bytes = base64.b64decode(b64_data)
    except Exception as e:
        await update.message.reply_text(f"❌ Không decode được ảnh QR: {e}")
        return

    bio = io.BytesIO(png_bytes)
    bio.name = "qr.png"
    await update.message.reply_photo(photo=bio)

    job_id = job_queue.add_job_if_no_active(
        job_type="qr",
        user_id=user_id,
        chat_id=chat_id,
        data={"qrcode_id": qrcode_id},
    )
    if job_id is None:
        active_job = job_queue.get_active_job_for_user(user_id, job_type="qr")
        if active_job:
            status_text = "đang chờ" if active_job.status == "pending" else "đang xử lý"
            await update.message.reply_text(
                f"⏸️ Bạn đã có job QR đang {status_text}!\n"
                f"📋 Job ID: {active_job.job_id[:8]}\n"
                f"⏳ Trạng thái: {active_job.status}\n"
                "Vui lòng đợi job hiện tại hoàn thành."
            )
        else:
            await update.message.reply_text(
                "⏸️ Bạn đã có job đang xử lý. Vui lòng đợi hoàn thành."
            )
        return

    processing_msg = await update.message.reply_text("⏳ Đang chờ quét QR...")
    asyncio.create_task(
        check_job_status(chat_id, job_id, job_queue, bot_app, processing_msg.message_id)
    )


async def check_job_status(chat_id: int, job_id: str, job_queue: JobQueue, bot_app: 'Application', processing_msg_id: int = None):
    """Polling \u0111\u1EC3 check job status v\u00E0 g\u1EEDi k\u1EBFt qu\u1EA3 khi ho\u00E0n th\u00E0nh.

    L\u01B0u \u00FD:
    - Tr\u01B0\u1EDBc \u0111\u00E2y polling gi\u1EDBi h\u1EA1n 30s d\u1EABn t\u1EDBi Timeout khi h\u00E0ng \u0111\u1EE3i d\u00E0i (nhi\u1EC1u user).
    - Hi\u1EC7n t\u1EA1i polling s\u1EBD ch\u1EA1y t\u1EDBi khi job completed/failed (c\u00F3 backoff nh\u1EB9),
      \u0111\u1EC3 tr\u00E1nh "timeout gi\u1EA3" khi job v\u1EABn \u0111ang ch\u1EDD/\u0111ang x\u1EED l\u00FD.
    """
    sleep_seconds = 1.0
    max_sleep_seconds = 5.0
    polls = 0
    
    while True:
        await asyncio.sleep(sleep_seconds)  # Check theo nh\u1ECBp hi\u1EC7n t\u1EA1i
        polls += 1
        if polls % 10 == 0 and sleep_seconds < max_sleep_seconds:
            sleep_seconds = min(max_sleep_seconds, sleep_seconds + 0.5)
        
        job = job_queue.get_job(job_id)
        if not job:
            break
            
        if job.status == "completed":
            # X\u00F3a tin nh\u1EAFn "Đang x\u1EED l\u00FD..." n\u1EBFu c\u00F3
            if processing_msg_id:
                try:
                    await bot_app.bot.delete_message(chat_id=chat_id, message_id=processing_msg_id)
                except Exception as e:
                    print(f"Kh\u00F4ng th\u1EC3 x\u00F3a tin nh\u1EAFn: {e}")
            
            # Job ho\u00E0n th\u00E0nh, g\u1EEDi k\u1EBFt qu\u1EA3
            result = job.result
            message = result.get("message", "Hello")
            message_format = result.get("message_format", "text")
            has_buttons = result.get("has_buttons", False)

            # Lưu creds nếu worker trả về (ví dụ /mailfree -> nút "Đọc email")
            try:
                store_creds = result.get("store_creds")
                if isinstance(store_creds, dict):
                    em = (store_creds.get("email") or "").strip()
                    pw = (store_creds.get("password") or "").strip()
                    if em and pw:
                        _email_creds[job_id] = {"email": em, "password": pw}
            except Exception:
                pass

            # /checkmail: luôn lưu email|password từ job (kể cả inbox rỗng) để callback email_read / email_info hoạt động
            if job.job_type == "checkmail" and isinstance(job.data, dict):
                em = (job.data.get("email") or "").strip()
                pw = (job.data.get("password") or "").strip()
                if em and pw:
                    _email_creds[job_id] = {"email": em, "password": pw}
            
            # N\u1EBFu c\u00F3 buttons (checkmail command)
            if has_buttons:
                emails = result.get("emails", [])
                if emails:
                    # T\u1EA1o inline keyboard buttons
                    button_rows = email_utils.create_email_buttons(len(emails), job_id)
                    keyboard = []
                    for row in button_rows:
                        keyboard.append([InlineKeyboardButton(**btn) for btn in row])
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    # L\u01B0u emails v\u00E0o module-level cache \u0111\u1EC3 c\u00F3 th\u1EC3 truy xu\u1EA5t khi click button
                    _email_cache[job_id] = emails

                    # Lưu credential để refresh inbox (email/password của /checkmail)
                    try:
                        if isinstance(job.data, dict):
                            em = (job.data.get("email") or "").strip()
                            pw = (job.data.get("password") or "").strip()
                            if em and pw:
                                _email_creds[job_id] = {"email": em, "password": pw}
                    except Exception:
                        pass
                    
                    await bot_app.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                else:
                    await bot_app.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML',
                    )
            elif message_format == "HTML":
                # N\u1EBFu message \u0111\u00E3 \u0111\u01B0\u1EE3c format HTML trong worker
                reply_markup = None
                try:
                    inline_keyboard = result.get("inline_keyboard")
                    if isinstance(inline_keyboard, list):
                        keyboard = []
                        for row in inline_keyboard:
                            if isinstance(row, list):
                                keyboard.append([InlineKeyboardButton(**btn) for btn in row])
                        if keyboard:
                            reply_markup = InlineKeyboardMarkup(keyboard)
                except Exception:
                    reply_markup = None

                await bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='HTML',
                    reply_markup=reply_markup,
                )
                store_creds = result.get("store_creds")  # cookie_text = "SPC_ST=..."
            cookie_for_orders = result.get("store_creds")
            if job.job_type in ("cks", "qr") and isinstance(cookie_for_orders, str) and cookie_for_orders.startswith("SPC_ST="):
                # chạy lấy đơn trong thread (blocking) — dùng cùng proxy worker đã trả về (login + API đơn)
                try:
                    print("Lấy đơn")
                    order_proxies = result.get("proxies")
                    if order_proxies is not None and not isinstance(order_proxies, dict):
                        order_proxies = None
                    orders = await asyncio.to_thread(
                        checkmvd.collect_orders,
                        cookie_for_orders,      # cookie
                        10,               # page_size
                        15,               # timeout
                        5,                # max_orders
                        False,            # include_logistics
                        order_proxies,    # proxies (http/https) — khớp handle_cks / get_user_best_proxy
                    )
                    # format message 2 (tránh quá dài)
                    msg = "📋 <b>Danh sách đơn hàng</b>\n\n"
                    for i, od in enumerate(orders[:3], start=1):
                        msg += f"{format_order_like_form(od)}\n\n— — —\n\n"
                    await bot_app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
                except Exception as e:
                    print(f"Lỗi lấy đơn (/cks hoặc /qr): {e}")
                    await bot_app.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "❌ <b>Lấy đơn bị lỗi</b>\n\n"
                            "Hãy báo cho admin biết có lỗi này nhé."
                        ),
                        parse_mode="HTML",
                    )
            elif not has_buttons and message_format != "HTML":
                # Chỉ job kiểu text đơn (vd. /cvc) — đã gửi HTML hoặc có nút thì KHÔNG gửi thêm (tránh trùng + lỗi hiển thị <b>)
                await bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=f"\u2705 Ho\u00E0n th\u00E0nh!\n{message}"
                )
            break
        elif job.status == "failed":
            # X\u00F3a tin nh\u1EAFn "Đang x\u1EED l\u00FD..." n\u1EBFu c\u00F3
            if processing_msg_id:
                try:
                    await bot_app.bot.delete_message(chat_id=chat_id, message_id=processing_msg_id)
                except Exception as e:
                    print(f"Kh\u00F4ng th\u1EC3 x\u00F3a tin nh\u1EAFn: {e}")
            
            # Job th\u1EA5t b\u1EA1i
            error = job.error or "L\u1ED7i kh\u00F4ng x\u00E1c \u0111\u1ECBnh"
            await bot_app.bot.send_message(
                chat_id=chat_id,
                text=f"\u274C L\u1ED7i: {error}"
            )
            break


async def checkmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE, job_queue: JobQueue, bot_app: 'Application'):
    """Handler cho command /checkmail"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    # Lấy dữ liệu từ context
    args = context.args  # List các tham số
    
    # Command format: /checkmail email|password
    if not args:
        await update.message.reply_text(
            "❌ Thiếu tham số!\n"
            "Cú pháp: /checkmail <email>|<password>\n"
            "Ví dụ: /checkmail chachi.palmares@fshare.dpdns.org|Lg65ztTcB4Ew"
        )
        return
    
    # Join tất cả args lại thành một chuỗi (để xử lý trường hợp có khoảng trắng trong password)
    input_str = " ".join(args)
    
    # Tách email và password bằng dấu |
    if "|" not in input_str:
        await update.message.reply_text(
            "❌ Format không đúng!\n"
            "Cú pháp: /checkmail <email>|<password>\n"
            "Ví dụ: /checkmail chachi.palmares@fshare.dpdns.org|Lg65ztTcB4Ew"
        )
        return
    
    parts = input_str.split("|", 1)  # Chỉ split ở dấu | đầu tiên
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Format không đúng!\n"
            "Cú pháp: /checkmail <email>|<password>\n"
            "Ví dụ: /checkmail chachi.palmares@fshare.dpdns.org|Lg65ztTcB4Ew"
        )
        return
    
    email = parts[0].strip()
    password = parts[1].strip()
    
    if not email or not password:
        await update.message.reply_text(
            "❌ Email hoặc password không được để trống!\n"
            "Cú pháp: /checkmail <email>|<password>\n"
            "Ví dụ: /checkmail chachi.palmares@fshare.dpdns.org|Lg65ztTcB4Ew"
        )
        return
    
    # Atomic operation: Check + Create trong cùng lock để tránh race condition
    job_id = job_queue.add_job_if_no_active(
        job_type="checkmail",
        user_id=user_id,
        chat_id=chat_id,
        data={
            "email": email,
            "password": password
        }
    )
    
    # Nếu job_id là None → User đã có job đang chạy
    if job_id is None:
        # Lấy job đang chạy để hiển thị thông tin
        active_job = job_queue.get_active_job_for_user(user_id, job_type="checkmail")
        if active_job:
            status_text = "đang chờ" if active_job.status == "pending" else "đang xử lý"
            await update.message.reply_text(
                f"⏸️ Bạn đã có job đang {status_text}!\n"
                f"📋 Job ID: {active_job.job_id[:8]}\n"
                f"⏳ Trạng thái: {active_job.status}\n"
                f"Vui lòng đợi job hiện tại hoàn thành trước khi gửi request mới."
            )
        else:
            await update.message.reply_text(
                "⏸️ Bạn đã có job đang xử lý. Vui lòng đợi job hiện tại hoàn thành."
            )
        return
    
    # Trả về ngay lập tức (không chờ xử lý)
    processing_msg = await update.message.reply_text(
        "⏳ Đang xử lý..."
    )
    processing_msg_id = processing_msg.message_id
    
    # Bắt đầu polling để check job status
    asyncio.create_task(check_job_status(chat_id, job_id, job_queue, bot_app, processing_msg_id))


async def mailfree_command(update: Update, context: ContextTypes.DEFAULT_TYPE, job_queue: JobQueue, bot_app: 'Application'):
    """
    Handler cho command /mailfree
    Tạo email free và add email vào cookie.

    Input hỗ trợ 2 dạng:
      - SPC_ST=... (cookie)
      - id|pass|spc_f (hoặc id|pass||spc_f) để extract SPC_ST trước
    """
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    args = context.args

    if not args:
        await update.message.reply_text(
            "❌ Thiếu tham số!\n"
            "Cú pháp:\n"
            "<code>/mailfree SPC_ST=...</code>\n"
            "hoặc\n"
            "<code>/mailfree id|pass|spc_f</code>",
            parse_mode="HTML",
        )
        return

    input_str = " ".join(args).strip()
    job_id = job_queue.add_job_if_no_active(
        job_type="mailfree",
        user_id=user_id,
        chat_id=chat_id,
        data={"input": input_str},
    )

    if job_id is None:
        active_job = job_queue.get_active_job_for_user(user_id, job_type="mailfree")
        if active_job:
            status_text = "đang chờ" if active_job.status == "pending" else "đang xử lý"
            await update.message.reply_text(
                f"⏸️ Bạn đã có job đang {status_text}!\n"
                f"📋 Job ID: {active_job.job_id[:8]}\n"
                f"⏳ Trạng thái: {active_job.status}\n"
                f"Vui lòng đợi job hiện tại hoàn thành trước khi gửi request mới."
            )
        else:
            await update.message.reply_text(
                "⏸️ Bạn đã có job đang xử lý. Vui lòng đợi job hiện tại hoàn thành."
            )
        return

    processing_msg = await update.message.reply_text("⏳ Đang xử lý...")
    asyncio.create_task(
        check_job_status(chat_id, job_id, job_queue, bot_app, processing_msg.message_id)
    )


async def newmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE, job_queue: JobQueue, bot_app: 'Application'):
    """
    /newmail — đăng ký inbox mới qua register_email_full (random local + password),
    không cần tham số và không cần proxy. Có nút Đọc email / Thông tin email.
    """
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id

    job_id = job_queue.add_job_if_no_active(
        job_type="newmail",
        user_id=user_id,
        chat_id=chat_id,
        data={},
    )

    if job_id is None:
        active_job = job_queue.get_active_job_for_user(user_id, job_type="newmail")
        if active_job:
            status_text = "đang chờ" if active_job.status == "pending" else "đang xử lý"
            await update.message.reply_text(
                f"⏸️ Bạn đã có job đang {status_text}!\n"
                f"📋 Job ID: {active_job.job_id[:8]}\n"
                f"⏳ Trạng thái: {active_job.status}\n"
                f"Vui lòng đợi job hiện tại hoàn thành trước khi gửi request mới."
            )
        else:
            await update.message.reply_text(
                "⏸️ Bạn đã có job đang xử lý. Vui lòng đợi job hiện tại hoàn thành."
            )
        return

    processing_msg = await update.message.reply_text("⏳ Đang tạo email mới...")
    asyncio.create_task(
        check_job_status(chat_id, job_id, job_queue, bot_app, processing_msg.message_id)
    )


async def email_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_app: 'Application', job_queue: JobQueue):
    """Handler cho callback query khi click button email"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    # Parse callback_data: email_detail_{job_id}_{email_index}
    # Format: email_detail_{job_id}_{email_index}
    if callback_data.startswith("email_detail_"):
        # Tách prefix và phần còn lại
        prefix = "email_detail_"
        remaining = callback_data[len(prefix):]
        
        # Tách từ cuối để lấy email_index (số cuối cùng)
        parts = remaining.rsplit("_", 1)
        if len(parts) == 2:
            job_id = parts[0]
            email_index = int(parts[1]) - 1  # Convert từ 1-based sang 0-based
            
            # Lấy emails từ cache
            if job_id in _email_cache:
                emails = _email_cache[job_id]
                
                # Sắp xếp emails từ mới đến cũ (giống như khi hiển thị list)
                def get_email_date(email):
                    date_str = email.get('date', '')
                    if not date_str:
                        return datetime.min.replace(tzinfo=timezone.utc)
                    try:
                        if date_str.endswith('Z'):
                            date_str = date_str[:-1] + '+00:00'
                        elif '+' not in date_str[-6:] and '-' not in date_str[-6:]:
                            date_str = date_str + '+00:00'
                        dt = datetime.fromisoformat(date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except:
                        return datetime.min.replace(tzinfo=timezone.utc)
                
                emails_sorted = sorted(emails, key=get_email_date, reverse=True)
                
                if 0 <= email_index < len(emails_sorted):
                    email_detail = emails_sorted[email_index]
                    detail_message = email_utils.format_email_detail(email_detail)
                    
                    # Kiểm tra xem có phải email cảnh báo đăng nhập không
                    email_type_info = email_utils.get_email_type_info(email_detail)
                    is_login_warning = email_type_info['type'] == 'login_warning'
                    
                    # Tạo buttons
                    if is_login_warning:
                        # Buttons đặc biệt cho email cảnh báo: "Xác minh tự động" và "Quay lại Inbox"
                        verify_button = InlineKeyboardButton(
                            text="🔒 Xác minh tự động",
                            callback_data=f"email_verify_{job_id}_{email_index}"
                        )
                        back_button = InlineKeyboardButton(
                            text="⬅️ Quay lại Inbox",
                            callback_data=f"email_list_{job_id}"
                        )
                        reply_markup = InlineKeyboardMarkup([[verify_button], [back_button]])
                    else:
                        # Button thông thường cho các email khác
                        back_button = InlineKeyboardButton(
                            text="⬅️ Quay lại",
                            callback_data=f"email_list_{job_id}"
                        )
                        reply_markup = InlineKeyboardMarkup([[back_button]])
                    
                    await query.edit_message_text(
                        text=detail_message,
                        parse_mode='HTML',
                        reply_markup=reply_markup
                    )
                else:
                    await query.answer("Email không tồn tại!", show_alert=True)
            else:
                await query.answer("Dữ liệu email đã hết hạn. Vui lòng gọi lại /checkmail", show_alert=True)
    
    elif callback_data.startswith("email_verify_"):
        # Xác minh tự động - lấy link xác minh và hiển thị
        prefix = "email_verify_"
        parts = callback_data[len(prefix):].split("_")
        if len(parts) >= 2:
            job_id = parts[0]
            email_index = int(parts[1])
            
            if job_id in _email_cache:
                emails = _email_cache[job_id]
                
                # Sắp xếp lại emails (giống như khi hiển thị)
                def get_email_date(email):
                    date_str = email.get('date', '')
                    if not date_str:
                        return datetime.min.replace(tzinfo=timezone.utc)
                    try:
                        if date_str.endswith('Z'):
                            date_str = date_str[:-1] + '+00:00'
                        elif '+' not in date_str[-6:] and '-' not in date_str[-6:]:
                            date_str = date_str + '+00:00'
                        dt = datetime.fromisoformat(date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except:
                        return datetime.min.replace(tzinfo=timezone.utc)
                
                emails_sorted = sorted(emails, key=get_email_date, reverse=True)
                
                if 0 <= email_index < len(emails_sorted):
                    email_detail = emails_sorted[email_index]
                    body_text = email_detail.get('body_text', '')
                    body_html = email_detail.get('body_html', '')
                    verification_link = email_utils.parse_verification_link_from_body(body_text, body_html)
                    
                    if verification_link:
                        await query.answer("Đang xử lý...", show_alert=False)

                        acc_raw = email_utils.parse_account_from_body(body_text)
                        device = email_utils.parse_device_from_body(body_text)
                        location = email_utils.parse_location_from_body(body_text)
                        acc_show = _mask_shopee_account(acc_raw)
                        time_show = _login_warning_time_display(email_detail)
                        dev_show = device.strip() if device else "—"
                        loc_show = location.strip() if location else "—"

                        success_text = (
                            "✅ <b>Xác minh thành công!</b>\n\n"
                            f"👤 <b>Tài khoản:</b> <code>{_escape(acc_show)}</code>\n"
                            f"🕐 <b>Thời gian:</b> {_escape(time_show)}\n"
                            f"💻 <b>Thiết bị:</b> {_escape(dev_show)}\n"
                            f"📍 <b>Vị trí:</b> {_escape(loc_show)}"
                        )
                        read_btn = InlineKeyboardButton(
                            text="📩 Đọc Mail",
                            callback_data=f"email_read_{job_id}",
                        )
                        reply_markup = InlineKeyboardMarkup([[read_btn]])

                        try:
                            await query.edit_message_text(
                                success_text,
                                parse_mode="HTML",
                                reply_markup=reply_markup,
                            )
                        except BadRequest as e:
                            if "not modified" not in str(e).lower():
                                raise

                        async def _background_verify() -> None:
                            try:
                                await asyncio.to_thread(verify_link, verification_link)
                            except Exception as e:
                                print(e)

                        asyncio.create_task(_background_verify())
                    else:
                        await query.answer("Không tìm thấy link xác minh trong email này", show_alert=True)
                else:
                    await query.answer("Email không tồn tại!", show_alert=True)
            else:
                await query.answer("Dữ liệu email đã hết hạn. Vui lòng gọi lại /checkmail", show_alert=True)
        else:
            await query.answer("Lỗi xử lý callback", show_alert=True)
    
    elif callback_data.startswith("email_refresh_"):
        # Refresh - gọi lại command checkmail
        prefix = "email_refresh_"
        job_id = callback_data[len(prefix):]
        creds = _email_creds.get(job_id) or {}
        email = (creds.get("email") or "").strip()
        password = (creds.get("password") or "").strip()

        # Fallback: lấy từ job_queue nếu cache chưa có
        if (not email or not password) and job_queue is not None:
            j = job_queue.get_job(job_id)
            if j and isinstance(j.data, dict):
                email = (j.data.get("email") or "").strip()
                password = (j.data.get("password") or "").strip()

        if not email or not password:
            await query.answer(
                "Không có thông tin đăng nhập inbox. Vui lòng gọi lại /checkmail",
                show_alert=True,
            )
            return

        await query.answer("Đang làm mới inbox...", show_alert=False)

        result = await asyncio.to_thread(email_utils.get_emails_from_tempmail, email, password)
        if result.get("status") == "error":
            await query.answer(
                f"Lỗi làm mới: {result.get('error', 'Không xác định')}",
                show_alert=True,
            )
            return

        emails = result.get("emails", []) or []
        _email_cache[job_id] = emails
        _email_creds[job_id] = {"email": email, "password": password}

        if not emails:
            try:
                await query.edit_message_text(
                    text="📭 Không có email nào trong hộp thư.",
                    parse_mode="HTML",
                    reply_markup=_empty_inbox_reply_markup(job_id),
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    await query.answer("Không có thay đổi.", show_alert=False)
                else:
                    raise
            return

        list_message = email_utils.format_emails_list(emails)
        button_rows = email_utils.create_email_buttons(len(emails), job_id)
        keyboard = []
        for row in button_rows:
            keyboard.append([InlineKeyboardButton(**btn) for btn in row])
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                text=list_message,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("Không có email mới.", show_alert=False)
            else:
                raise

    elif callback_data.startswith("email_read_"):
        # Đọc email (dùng creds đã lưu) và hiển thị UI như /checkmail
        prefix = "email_read_"
        job_id = callback_data[len(prefix):]

        creds = _email_creds.get(job_id) or {}
        email = (creds.get("email") or "").strip()
        password = (creds.get("password") or "").strip()

        if not email or not password:
            await query.answer(
                "Không có thông tin đăng nhập inbox. Vui lòng gọi lại /checkmail",
                show_alert=True,
            )
            return

        await query.answer("Đang đọc inbox...", show_alert=False)
        result = await asyncio.to_thread(email_utils.get_emails_from_tempmail, email, password)
        if result.get("status") == "error":
            await query.answer(
                f"Lỗi đọc inbox: {result.get('error', 'Không xác định')}",
                show_alert=True,
            )
            return

        emails = result.get("emails", []) or []
        _email_cache[job_id] = emails

        if not emails:
            try:
                await query.edit_message_text(
                    text="📭 Không có email nào trong hộp thư.",
                    parse_mode="HTML",
                    reply_markup=_empty_inbox_reply_markup(job_id),
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    await query.answer("Không có thay đổi.", show_alert=False)
                else:
                    raise
            return

        list_message = email_utils.format_emails_list(emails)
        button_rows = email_utils.create_email_buttons(len(emails), job_id)
        keyboard = []
        for row in button_rows:
            keyboard.append([InlineKeyboardButton(**btn) for btn in row])
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                text=list_message,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("Không có email mới.", show_alert=False)
            else:
                raise
    
    elif callback_data.startswith("email_list_"):
        # Quay lại danh sách email (nếu chưa có cache — vd. /newmail → Thông tin → Quay lại — thì fetch inbox trước)
        prefix = "email_list_"
        job_id = callback_data[len(prefix):]

        emails: list | None = None
        if job_id in _email_cache:
            emails = _email_cache[job_id]
        else:
            creds = _email_creds.get(job_id) or {}
            email = (creds.get("email") or "").strip()
            password = (creds.get("password") or "").strip()
            if (not email or not password) and job_queue is not None:
                j = job_queue.get_job(job_id)
                if j and isinstance(j.data, dict):
                    email = (j.data.get("email") or "").strip()
                    password = (j.data.get("password") or "").strip()
            if not email or not password:
                try:
                    await query.edit_message_text(
                        text="❌ Chưa có dữ liệu inbox. Vui lòng gọi lại <code>/checkmail</code> hoặc <code>/newmail</code>.",
                        parse_mode="HTML",
                    )
                except BadRequest:
                    pass
                return
            result = await asyncio.to_thread(
                email_utils.get_emails_from_tempmail, email, password
            )
            if result.get("status") == "error":
                err = html.escape(str(result.get("error", "Không xác định")))[:500]
                try:
                    await query.edit_message_text(
                        text=f"❌ Lỗi đọc inbox: <code>{err}</code>",
                        parse_mode="HTML",
                    )
                except BadRequest:
                    pass
                return
            emails = result.get("emails", []) or []
            _email_cache[job_id] = emails
            _email_creds[job_id] = {"email": email, "password": password}

        list_message = email_utils.format_emails_list(emails)
        if not emails:
            reply_markup = _empty_inbox_reply_markup(job_id)
        else:
            button_rows = email_utils.create_email_buttons(len(emails), job_id)
            keyboard = []
            for row in button_rows:
                keyboard.append([InlineKeyboardButton(**btn) for btn in row])
            reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                text=list_message,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("Không có thay đổi.", show_alert=False)
            else:
                raise
    
    elif callback_data.startswith("email_info_"):
        # Hiển thị thông tin mail (email/pass) theo format chuẩn
        prefix = "email_info_"
        job_id = callback_data[len(prefix):]

        creds = _email_creds.get(job_id) or {}
        email = (creds.get("email") or "").strip()
        password = (creds.get("password") or "").strip()

        if not email or not password:
            try:
                await query.edit_message_text(
                    text="❌ Không có thông tin mail. Vui lòng gọi lại <code>/checkmail</code>, <code>/mailfree</code> hoặc <code>/newmail</code>.",
                    parse_mode="HTML",
                )
            except BadRequest:
                pass
            return

        info_text = (
            "<b>THÔNG TIN MAIL</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"📧 <b>Email</b>: <code>{email}</code>\n"
            f"🔐 <b>Pass</b>: <code>{password}</code>\n"
            f"📋 <b>Copy</b>: <code>{email}|{password}</code>\n"
            "━━━━━━━━━━━━━━"
        )

        # Buttons: Đọc Mail + Quay lại Inbox
        read_btn = InlineKeyboardButton(
            text="📩 Đọc Mail",
            callback_data=f"email_read_{job_id}",
        )
        back_btn = InlineKeyboardButton(
            text="⬅️ Quay lại Inbox",
            callback_data=f"email_list_{job_id}",
        )
        reply_markup = InlineKeyboardMarkup([[read_btn], [back_btn]])

        try:
            await query.edit_message_text(
                text=info_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("Không có thay đổi.", show_alert=False)
            else:
                raise


async def queue_status(update: Update, context: ContextTypes.DEFAULT_TYPE, job_queue: JobQueue):
    """Command \u0111\u1EC3 xem tr\u1EA1ng th\u00E1i queue"""
    queue_size = job_queue.get_queue_size()
    active_jobs = job_queue.get_active_jobs_count()
    await update.message.reply_text(
        f"\U0001F4CA Queue Status:\n"
        f"\u2022 Pending jobs: {queue_size}\n"
        f"\u2022 Active jobs: {active_jobs}\n"
        f"\u2022 Workers: {job_queue.max_workers}"
    )


async def kipx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lưu / xem KiotProxy key riêng cho từng user.

    Cú pháp:
      - /kipx
            Xem KiotProxy key đang lưu cho user hiện tại (nếu có).
      - /kipx <key>
            Lưu / cập nhật KiotProxy key cho user hiện tại.
    """
    user = update.effective_user
    if not user:
        await update.message.reply_text("❌ Không lấy được thông tin user.")
        return

    user_id = user.id

    # Không có tham số -> xem KiotProxy key hiện tại
    if not context.args:
        existing_key = get_user_proxy_key(user_id, "kiot")
        if not existing_key:
            await update.message.reply_text(
                "📭 Bạn chưa lưu KiotProxy key nào.\n"
                "Lưu bằng cú pháp:\n"
                "<code>/kipx your_kiotproxy_key_here</code>",
                parse_mode="HTML",
            )
            return

        await update.message.reply_text(
            "🔑 KiotProxy key hiện tại của bạn là:\n"
            f"<code>{existing_key}</code>",
            parse_mode="HTML",
        )
        return

    # Có tham số -> lưu / cập nhật KiotProxy key (gộp tất cả args còn lại thành key)
    proxy_key = " ".join(context.args).strip()

    if not proxy_key:
        await update.message.reply_text(
            "❌ Key không hợp lệ.\n"
            "Cú pháp: <code>/kipx your_kiotproxy_key_here</code>",
            parse_mode="HTML",
        )
        return

    # Lưu KiotProxy key với proxy_type cố định là 'kiot'
    save_user_proxy_key(user_id, "kiot", proxy_key)

    await update.message.reply_text(
        "✅ Đã lưu KiotProxy key cho bạn.\n"
        "Bạn có thể xem lại bằng lệnh: <code>/kipx</code>",
        parse_mode="HTML",
    )


async def vnpx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lưu / xem VNProxy key (hoặc một loại proxy khác) riêng cho từng user.

    Cú pháp:
      - /vnpx
            Xem VNProxy key đang lưu cho user hiện tại (nếu có).
      - /vnpx <key>
            Lưu / cập nhật VNProxy key cho user hiện tại.
    """
    user = update.effective_user
    if not user:
        await update.message.reply_text("❌ Không lấy được thông tin user.")
        return

    user_id = user.id
    # Không có tham số -> xem VNProxy key hiện tại
    if not context.args:
        existing_key = get_user_proxy_key(user_id, "vnpx")
        if not existing_key:
            await update.message.reply_text(
                "📭 Bạn chưa lưu VNProxy key nào.\n"
                "Lưu bằng cú pháp:\n"
                "<code>/vnpx your_vnproxy_key_here</code>",
                parse_mode="HTML",
            )
            return

        await update.message.reply_text(
            "🔑 VNProxy key hiện tại của bạn là:\n"
            f"<code>{existing_key}</code>",
            parse_mode="HTML",
        )
        return

    # Có tham số -> lưu / cập nhật VNProxy key (gộp tất cả args lại thành key)
    proxy_key = " ".join(context.args).strip()

    if not proxy_key:
        await update.message.reply_text(
            "❌ Key không hợp lệ.\n"
            "Cú pháp: <code>/vnpx your_vnproxy_key_here</code>",
            parse_mode="HTML",
        )
        return

    # Lưu VNProxy key với proxy_type cố định là 'vnpx'
    save_user_proxy_key(user_id, "vnpx", proxy_key)

    await update.message.reply_text(
        "✅ Đã lưu VNProxy key cho bạn.\n"
        "Bạn có thể xem lại bằng lệnh: <code>/vnpx</code>",
        parse_mode="HTML",
    )


async def delpx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xóa toàn bộ proxy (mọi loại key và cache) cho user hiện tại.

    Cú pháp:
      - /delpx
            Xóa tất cả proxy keys (kiot, vnpx, vnpx_proxy, ...) của user.
    """
    user = update.effective_user
    if not user:
        await update.message.reply_text("❌ Không lấy được thông tin user.")
        return

    user_id = user.id
    delete_user_proxies(user_id)

    await update.message.reply_text(
        "🗑️ Đã xóa toàn bộ proxy keys của bạn.\n"
        "Bạn có thể thiết lập lại bằng /kipx và /vnpx.",
        parse_mode="HTML",
    )


async def vc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Lưu batch voucher mall: ``user|pass|sdt|SPC_F=...`` → lấy SPC_ST qua proxy,
    hoặc ``SPC_ST=...`` / chỉ giá trị SPC_ST. Gọi ``save_voucher_batch`` với
    ``VOUCHER_BATCH_LIST_HARDCODED`` (proxy bắt buộc).
    """
    if not update.message:
        return
    user = update.effective_user
    if not user:
        await update.message.reply_text("❌ Không lấy được thông tin user.")
        return

    user_id = user.id
    raw = " ".join(context.args or []).strip()
    if not raw:
        await update.message.reply_text(
            "❌ Thiếu tham số.\n"
            "Cú pháp:\n"
            "<code>/vc user|pass|sdt|SPC_F=...</code>\n"
            "hoặc <code>/vc SPC_ST=...</code> / chỉ giá trị SPC_ST",
            parse_mode="HTML",
        )
        return

    proxies, _src = get_user_best_proxy(user_id)
    if not proxies:
        await update.message.reply_text(
            "❌ Cần cấu hình proxy (<code>/kipx</code> hoặc <code>/vnpx</code>) trước.",
            parse_mode="HTML",
        )
        return

    chat_id = update.effective_chat.id
    processing_msg = await update.message.reply_text("⏳ Đang xử lý...")

    try:
        from save_voucher import format_vc_telegram_html, save_voucher_batch
        from voucher_status import VOUCHER_BATCH_LIST_HARDCODED

        cookie_header: Optional[str] = None

        if "|" in raw and "SPC_F" in raw.upper():
            try:
                spc_st_val = await asyncio.to_thread(login.extract_spc_st, raw, proxies)
            except ValueError as e:
                await update.message.reply_text(
                    "❌ <b>Lấy cookie SPC_ST thất bại</b>\n\n"
                    f"Định dạng hoặc thiếu trường: {html.escape(str(e))}\n\n"
                    "<i>Cần đúng:</i> <code>user|pass|sdt|SPC_F=...</code>",
                    parse_mode="HTML",
                )
                return
            except Exception as e:
                detail = html.escape(str(e))
                await update.message.reply_text(
                    "❌ <b>Lấy cookie SPC_ST thất bại</b>\n\n"
                    f"Chi tiết: <code>{detail}</code>\n\n"
                    "<i>Gợi ý:</i> kiểm tra user, mật khẩu, <code>SPC_F</code> còn hiệu lực; "
                    "thử proxy khác (<code>/kipx</code>, <code>/vnpx</code>); "
                    "hoặc gửi sẵn <code>SPC_ST=...</code> nếu đã có cookie.",
                    parse_mode="HTML",
                )
                return
            if not spc_st_val or not str(spc_st_val).strip():
                await update.message.reply_text(
                    "❌ <b>Lấy cookie SPC_ST thất bại</b>\n\n"
                    "Shopee không trả về <code>SPC_ST</code> (chuỗi rỗng). "
                    "Thử đăng nhập lại trên web/app để lấy <code>SPC_F</code> mới.",
                    parse_mode="HTML",
                )
                return
            cookie_header = f"SPC_ST={spc_st_val}"
        elif "SPC_ST=" in raw.upper():
            cookie_header = raw.strip()
        elif "|" not in raw:
            st_only = raw.strip()
            if not st_only:
                await update.message.reply_text(
                    "❌ Thiếu giá trị <code>SPC_ST</code>.",
                    parse_mode="HTML",
                )
                return
            cookie_header = f"SPC_ST={st_only}"
        else:
            await update.message.reply_text(
                "❌ Định dạng không hợp lệ.\n"
                "Dùng: <code>user|pass|sdt|SPC_F=...</code> hoặc <code>SPC_ST=...</code>",
                parse_mode="HTML",
            )
            return

        ch = (cookie_header or "").strip()
        if ch.upper().startswith("SPC_ST="):
            _st_val = ch.split("=", 1)[-1].strip()
            if not _st_val:
                await update.message.reply_text(
                    "❌ <b>Lấy cookie SPC_ST thất bại</b>\n\n"
                    "Giá trị sau <code>SPC_ST=</code> đang trống.",
                    parse_mode="HTML",
                )
                return

        cookie_header = ch
        spc_st_esc = html.escape(cookie_header)

        results = await asyncio.to_thread(
            save_voucher_batch,
            VOUCHER_BATCH_LIST_HARDCODED,
            cookie_header=cookie_header,
            csrftoken=None,
            proxies=proxies,
        )

        body = format_vc_telegram_html(results)
        text = (
            "✅ <b>Login thành công!</b>\n\n"
            f"<code>{spc_st_esc}</code>\n\n"
            "📝 <b>KẾT QUẢ LƯU VOUCHER</b>\n\n"
            f"{body}"
        )

        if len(text) <= 4096:
            await update.message.reply_text(text, parse_mode="HTML")
        else:
            chunk0 = text[:4096]
            rest = text[4096:]
            await update.message.reply_text(chunk0, parse_mode="HTML")
            for i in range(0, len(rest), 4096):
                await update.message.reply_text(rest[i : i + 4096], parse_mode="HTML")
    finally:
        try:
            await context.bot.delete_message(
                chat_id=chat_id, message_id=processing_msg.message_id
            )
        except Exception:
            pass


def build_spx_inline_keyboard(spx_tn: str, *, expanded: bool) -> InlineKeyboardMarkup:
    """Nút SPX: chi tiết/thu gọn, làm mới, thống kê, hướng dẫn, theo dõi."""
    detail_btn = InlineKeyboardButton(
        "📜 Thu gọn" if expanded else "📜 Xem lịch sử chi tiết",
        callback_data=f"spx_c|{spx_tn}" if expanded else f"spx_d|{spx_tn}",
    )
    return InlineKeyboardMarkup(
        [
            [detail_btn, InlineKeyboardButton("🔄 Làm mới", callback_data=f"spx_r|{spx_tn}")],
            [
                InlineKeyboardButton("📊 Thống kê", callback_data=f"spx_s|{spx_tn}"),
                InlineKeyboardButton("❓ Hướng dẫn", callback_data=f"spx_h|{spx_tn}"),
            ],
            [InlineKeyboardButton("🚩 Theo dõi liên tục", callback_data=f"spx_w|{spx_tn}")],
        ]
    )


async def spx_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback inline SPX: chi tiết / thu gọn / làm mới / stub các nút còn lại."""
    q = update.callback_query
    if not q or not q.data:
        return

    data_cb = q.data
    if not re.match(r"^spx_[dcrshw]\|", data_cb):
        return

    parts = data_cb.split("|", 1)
    if len(parts) != 2:
        await q.answer()
        return
    action, spx_tn = parts[0], parts[1]

    if action in ("spx_s", "spx_h", "spx_w"):
        await q.answer("Tính năng đang phát triển.", show_alert=True)
        return

    async def _fetch():
        return await asyncio.to_thread(spx.get_order_info_spx, spx_tn)

    if action == "spx_r":
        try:
            payload, api_err = await _fetch()
        except Exception as exc:
            await q.answer(f"Lỗi: {exc}", show_alert=True)
            return
        if payload is None:
            await q.answer(api_err or "Lỗi không xác định", show_alert=True)
            return
        summary = spx.format_spx_summary_html(payload, spx_tn=spx_tn)
        if api_err:
            summary += f"\n\n⚠️ {_escape(api_err)}"
        try:
            await q.edit_message_text(
                summary,
                parse_mode="HTML",
                reply_markup=build_spx_inline_keyboard(spx_tn, expanded=False),
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        await q.answer()
        return

    if action == "spx_d":
        try:
            payload, api_err = await _fetch()
        except Exception as exc:
            await q.answer(f"Lỗi: {exc}", show_alert=True)
            return
        if payload is None:
            await q.answer(api_err or "Lỗi không xác định", show_alert=True)
            return
        suffix = f"\n\n⚠️ {_escape(api_err)}" if api_err else ""
        reserve = len(suffix)
        max_body = max(1, spx.TELEGRAM_MAX_MESSAGE_CHARS - reserve)
        body = spx.format_spx_delivery_history(payload, max_chars=max_body)
        text = _escape(body)
        try:
            await q.edit_message_text(
                text + suffix,
                parse_mode="HTML",
                reply_markup=build_spx_inline_keyboard(spx_tn, expanded=True),
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        await q.answer()
        return

    if action == "spx_c":
        try:
            payload, api_err = await _fetch()
        except Exception as exc:
            await q.answer(f"Lỗi: {exc}", show_alert=True)
            return
        if payload is None:
            await q.answer(api_err or "Lỗi không xác định", show_alert=True)
            return
        summary = spx.format_spx_summary_html(payload, spx_tn=spx_tn)
        if api_err:
            summary += f"\n\n⚠️ {_escape(api_err)}"
        try:
            await q.edit_message_text(
                summary,
                parse_mode="HTML",
                reply_markup=build_spx_inline_keyboard(spx_tn, expanded=False),
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        await q.answer()
        return

    await q.answer()


async def spx_tracking_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Tin nhắn text bắt đầu bằng SPX hoặc VN → tra API SPX và trả tóm tắt + nút,
    reply ngay tại tin nhắn đó.
    """
    msg = update.effective_message
    if not msg or not msg.text:
        return

    spx_tn = spx.extract_spx_tracking_from_text(msg.text)
    if not spx_tn:
        await msg.reply_text(
            "❌ Không đọc được mã vận đơn. Gửi dạng: <code>SPX...</code> hoặc <code>VN...</code>",
            parse_mode="HTML",
            reply_to_message_id=msg.message_id,
        )
        return

    try:
        data, api_err = await asyncio.to_thread(spx.get_order_info_spx, spx_tn)
    except Exception as exc:
        await msg.reply_text(
            f"❌ Lỗi khi gọi API: {_escape(exc)}",
            reply_to_message_id=msg.message_id,
        )
        return

    if data is None:
        await msg.reply_text(
            f"❌ {api_err or 'Lỗi không xác định'}",
            reply_to_message_id=msg.message_id,
        )
        return

    summary = spx.format_spx_summary_html(data, spx_tn=spx_tn)
    if api_err:
        summary += f"\n\n⚠️ {_escape(api_err)}"

    await msg.reply_text(
        summary,
        parse_mode="HTML",
        reply_markup=build_spx_inline_keyboard(spx_tn, expanded=False),
        reply_to_message_id=msg.message_id,
    )


def build_ghn_inline_keyboard(ghn_order_code: str, *, expanded: bool) -> InlineKeyboardMarkup:
    """Nút GHN: chi tiết/thu gọn, làm mới, thống kê, hướng dẫn, theo dõi."""
    detail_btn = InlineKeyboardButton(
        "📜 Thu gọn" if expanded else "📜 Xem lịch sử chi tiết",
        callback_data=f"ghn_c|{ghn_order_code}" if expanded else f"ghn_d|{ghn_order_code}",
    )
    return InlineKeyboardMarkup(
        [
            [detail_btn, InlineKeyboardButton("🔄 Làm mới", callback_data=f"ghn_r|{ghn_order_code}")],
            [
                InlineKeyboardButton("📊 Thống kê", callback_data=f"ghn_s|{ghn_order_code}"),
                InlineKeyboardButton("❓ Hướng dẫn", callback_data=f"ghn_h|{ghn_order_code}"),
            ],
            [InlineKeyboardButton("🚩 Theo dõi liên tục", callback_data=f"ghn_w|{ghn_order_code}")],
        ]
    )


async def ghn_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback inline GHN: chi tiết / thu gọn / làm mới (các nút khác báo đang phát triển)."""
    q = update.callback_query
    if not q or not q.data:
        return

    data_cb = q.data
    if not re.match(r"^ghn_[dcrshw]\|", data_cb):
        return

    parts = data_cb.split("|", 1)
    if len(parts) != 2:
        await q.answer()
        return
    action, ghn_order_code = parts[0], parts[1]

    if action in ("ghn_s", "ghn_h", "ghn_w"):
        await q.answer("Tính năng đang phát triển.", show_alert=True)
        return

    async def _fetch():
        return await asyncio.to_thread(ghn.get_ghn_tracking_logs, ghn_order_code)

    if action in ("ghn_r", "ghn_c"):
        try:
            payload, api_err = await _fetch()
        except Exception as exc:
            await q.answer(f"Lỗi: {exc}", show_alert=True)
            return
        if payload is None:
            await q.answer(api_err or "Lỗi không xác định", show_alert=True)
            return

        summary = ghn.format_ghn_summary_html(payload, order_code=ghn_order_code)
        if api_err:
            summary += f"\n\n⚠️ {_escape(api_err)}"

        try:
            await q.edit_message_text(
                summary,
                parse_mode="HTML",
                reply_markup=build_ghn_inline_keyboard(ghn_order_code, expanded=False),
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        await q.answer()
        return

    if action == "ghn_d":
        try:
            payload, api_err = await _fetch()
        except Exception as exc:
            await q.answer(f"Lỗi: {exc}", show_alert=True)
            return
        if payload is None:
            await q.answer(api_err or "Lỗi không xác định", show_alert=True)
            return

        suffix = f"\n\n⚠️ {_escape(api_err)}" if api_err else ""
        reserve = len(suffix)
        max_body = max(1, ghn.TELEGRAM_MAX_MESSAGE_CHARS - reserve)
        body = ghn.format_ghn_delivery_history(payload, max_chars=max_body)
        text = _escape(body)

        try:
            await q.edit_message_text(
                text + suffix,
                parse_mode="HTML",
                reply_markup=build_ghn_inline_keyboard(ghn_order_code, expanded=True),
            )
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                raise
        await q.answer()
        return

    await q.answer()


async def ghn_tracking_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Tin nhắn text dạng `G` + đúng 8 ký tự (vd. GY4RPCNV) → tra API và trả tóm tắt + nút.
    """
    msg = update.effective_message
    if not msg or not msg.text:
        return

    ghn_order_code = msg.text.strip()
    if not (ghn_order_code and len(ghn_order_code) == 8 and ghn_order_code[0].upper() == "G"):
        return

    try:
        data, api_err = await asyncio.to_thread(ghn.get_ghn_tracking_logs, ghn_order_code)
    except Exception as exc:
        await msg.reply_text(
            f"❌ Lỗi khi gọi API: {_escape(exc)}",
            reply_to_message_id=msg.message_id,
        )
        return

    if data is None:
        await msg.reply_text(
            f"❌ {api_err or 'Lỗi không xác định'}",
            reply_to_message_id=msg.message_id,
        )
        return

    summary = ghn.format_ghn_summary_html(data, order_code=ghn_order_code)
    if api_err:
        summary += f"\n\n⚠️ {_escape(api_err)}"

    await msg.reply_text(
        summary,
        parse_mode="HTML",
        reply_markup=build_ghn_inline_keyboard(ghn_order_code, expanded=False),
        reply_to_message_id=msg.message_id,
    )


def setup_commands(application: 'Application', job_queue: JobQueue):
    """
    \u0110\u0103ng k\u00FD t\u1EA5t c\u1EA3 c\u00E1c command handlers v\u1EDBi application
    
    Args:
        application: Telegram bot application instance
        job_queue: JobQueue instance \u0111\u1EC3 x\u1EED l\u00FD jobs
    """
    # T\u1EA1o wrapper functions \u0111\u1EC3 inject dependencies
    async def cvc_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await cvc_command(update, context, job_queue, application)
    
    async def cks_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await cks_command(update, context, job_queue, application)

    async def qr_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await qr_command(update, context, job_queue, application)
    
    async def checkmail_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await checkmail_command(update, context, job_queue, application)

    async def mailfree_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await mailfree_command(update, context, job_queue, application)

    async def newmail_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await newmail_command(update, context, job_queue, application)
    
    async def queue_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await queue_status(update, context, job_queue)
    
    async def email_callback_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await email_callback_handler(update, context, application, job_queue)

    async def spx_callback_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await spx_callback_handler(update, context)

    async def ghn_callback_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await ghn_callback_handler(update, context)

    async def vc_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await vc_command(update, context)

    # Tin nhắn bắt đầu bằng SPX hoặc VN → tra SPX (không phải lệnh /...)
    spx_text_filter = (
        filters.TEXT
        & ~filters.COMMAND
        & filters.Regex(re.compile(r"^(?:SPX|VN)", re.IGNORECASE))
    )

    # \u0110\u0103ng k\u00FD handlers
    # Tin nhắn bắt đầu bằng G và có đúng 8 ký tự → GHN tracking (vd. GY4RPCNV)
    ghn_text_filter = (
        filters.TEXT
        & ~filters.COMMAND
        & filters.Regex(re.compile(r"^G[A-Za-z0-9]{7}$"))
    )

    application.add_handler(CommandHandler("cvc", cvc_wrapper))
    application.add_handler(CommandHandler("cks", cks_wrapper))
    application.add_handler(CommandHandler("qr", qr_wrapper))
    application.add_handler(CommandHandler("checkmail", checkmail_wrapper))
    application.add_handler(CommandHandler("mailfree", mailfree_wrapper))
    application.add_handler(CommandHandler("newmail", newmail_wrapper))
    application.add_handler(CommandHandler("queue", queue_wrapper))
    application.add_handler(CommandHandler("kipx", kipx_command))
    application.add_handler(CommandHandler("vnpx", vnpx_command))
    application.add_handler(CommandHandler("delpx", delpx_command))
    application.add_handler(CommandHandler("vc", vc_wrapper))
    application.add_handler(CallbackQueryHandler(email_callback_wrapper, pattern="^email_"))
    application.add_handler(CallbackQueryHandler(spx_callback_wrapper, pattern=r"^spx_[dcrshw]\|"))
    application.add_handler(MessageHandler(spx_text_filter, spx_tracking_message_handler))
    application.add_handler(CallbackQueryHandler(ghn_callback_wrapper, pattern=r"^ghn_[dcrshw]\|"))
    application.add_handler(MessageHandler(ghn_text_filter, ghn_tracking_message_handler))

