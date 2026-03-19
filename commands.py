# -*- coding: utf-8 -*-
"""
Command handlers cho Telegram Bot
T\u1EA5t c\u1EA3 c\u00E1c command handlers \u0111\u01B0\u1EE3c \u0111\u1ECBnh ngh\u0129a \u1EDF \u0111\u00E2y
"""

import asyncio
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from job_queue import JobQueue
from typing import TYPE_CHECKING
import email_utils
from proxy_storage import save_user_proxy_key, get_user_proxy_key, delete_user_proxies
import verify_mail

if TYPE_CHECKING:
    from telegram.ext import Application

# Module-level cache để lưu emails theo job_id
# Format: {job_id: [emails_list]}
_email_cache: dict[str, list] = {}
# Lưu credential để refresh inbox theo job_id
# Format: {job_id: {"email": "...", "password": "..."}}
_email_creds: dict[str, dict[str, str]] = {}

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
                        parse_mode='HTML'
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
            else:
                # Format m\u1EB7c \u0111\u1ECBnh
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
                        # Hiển thị thông báo đang xử lý
                        await query.answer("Đang xử lý...", show_alert=False)

                        # Dùng verify_mail.py (Playwright) thay cho call_verification_link
                        try:
                            await asyncio.to_thread(verify_mail.verify_link, verification_link)
                            message = "✅ <b>Xác minh thành công!</b>\n\n"
                            read_btn = InlineKeyboardButton(
                                text="📩 Đọc Mail",
                                callback_data=f"email_read_{job_id}",
                            )
                            reply_markup = InlineKeyboardMarkup([[read_btn]])
                            await query.message.reply_text(
                                message,
                                parse_mode="HTML",
                                reply_markup=reply_markup,
                            )
                        except Exception as e:
                            print(e)
                            message = "❌ <b>Xác minh thất bại</b>\n\n"
                            await query.message.reply_text(
                                message,
                                parse_mode="HTML",
                            )
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
        # Quay lại danh sách email
        prefix = "email_list_"
        job_id = callback_data[len(prefix):]
        
        if job_id in _email_cache:
            emails = _email_cache[job_id]
            list_message = email_utils.format_emails_list(emails)
            
            # Tạo lại buttons cho danh sách
            button_rows = email_utils.create_email_buttons(len(emails), job_id)
            keyboard = []
            for row in button_rows:
                keyboard.append([InlineKeyboardButton(**btn) for btn in row])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await query.edit_message_text(
                    text=list_message,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    await query.answer("Không có thay đổi.", show_alert=False)
                else:
                    raise
        else:
            await query.answer("Dữ liệu email đã hết hạn. Vui lòng gọi lại /checkmail", show_alert=True)
    
    elif callback_data.startswith("email_info_"):
        # Hiển thị thông tin mail (email/pass) theo format chuẩn
        prefix = "email_info_"
        job_id = callback_data[len(prefix):]

        creds = _email_creds.get(job_id) or {}
        email = (creds.get("email") or "").strip()
        password = (creds.get("password") or "").strip()

        if not email or not password:
            await query.answer(
                "Không có thông tin mail. Vui lòng gọi lại /checkmail hoặc /mailfree.",
                show_alert=True,
            )
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
    
    async def checkmail_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await checkmail_command(update, context, job_queue, application)

    async def mailfree_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await mailfree_command(update, context, job_queue, application)
    
    async def queue_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await queue_status(update, context, job_queue)
    
    async def email_callback_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await email_callback_handler(update, context, application, job_queue)
    
    # \u0110\u0103ng k\u00FD handlers
    application.add_handler(CommandHandler("cvc", cvc_wrapper))
    application.add_handler(CommandHandler("cks", cks_wrapper))
    application.add_handler(CommandHandler("checkmail", checkmail_wrapper))
    application.add_handler(CommandHandler("mailfree", mailfree_wrapper))
    application.add_handler(CommandHandler("queue", queue_wrapper))
    application.add_handler(CommandHandler("kipx", kipx_command))
    application.add_handler(CommandHandler("vnpx", vnpx_command))
    application.add_handler(CommandHandler("delpx", delpx_command))
    application.add_handler(CallbackQueryHandler(email_callback_wrapper, pattern="^email_"))

