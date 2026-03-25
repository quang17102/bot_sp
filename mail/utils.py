# -*- coding: utf-8 -*-
"""
Utilities cho việc xử lý email từ TempMail API
"""

import html
import re
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import time

try:
    from . import api
except ImportError:
    # python mail/utils.py — không có parent package
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from mail import api


def format_timestamp_for_email(iso_string: str) -> str:
    """Format ISO timestamp sang HH:MM DD-MM (múi giờ Việt Nam UTC+7)"""
    try:
        if not iso_string:
            return ""
        # Parse ISO string
        if iso_string.endswith('Z'):
            iso_string = iso_string[:-1] + '+00:00'
        elif '+' not in iso_string[-6:] and '-' not in iso_string[-6:]:
            iso_string = iso_string + '+00:00'
        
        dt = datetime.fromisoformat(iso_string)
        
        # Convert sang múi giờ Việt Nam (UTC+7)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        vietnam_tz = timezone(timedelta(hours=7))
        dt_vietnam = dt.astimezone(vietnam_tz)
        
        return dt_vietnam.strftime('%H:%M %d-%m')
    except Exception as e:
        return iso_string


def parse_device_from_body(body_text: str) -> Optional[str]:
    """Parse device từ body_text của email cảnh báo"""
    if not body_text:
        return None
    
    # Tìm pattern: "Trình duyệt/Thiết bị: ..."
    pattern = r'Trình duyệt/Thiết bị:\s*([^\n]+)'
    match = re.search(pattern, body_text)
    if match:
        device = match.group(1).strip()
        return device
    return None


def parse_account_from_body(body_text: str) -> Optional[str]:
    """Parse tài khoản từ body_text của email cảnh báo"""
    if not body_text:
        return None
    
    # Tìm pattern: "Tài khoản: ..." (có thể cùng dòng với "Thời gian truy cập:", cắt bỏ phần dư)
    pattern = r'Tài khoản:\s*([^\n]+)'
    match = re.search(pattern, body_text)
    if match:
        account = match.group(1).strip()
        # Bỏ phần dư nếu bị dính "_Thời gian truy cập: ..." (cùng dòng trong email)
        if "_Thời gian truy cập" in account:
            account = account.split("_Thời gian truy cập")[0].strip()
        if "Thời gian truy cập" in account:
            account = account.split("Thời gian truy cập")[0].strip()
        return account if account else None
    return None


def parse_location_from_body(body_text: str) -> Optional[str]:
    """Parse vị trí từ body_text của email cảnh báo"""
    if not body_text:
        return None
    
    # Tìm pattern: "Vị trí: ..."
    pattern = r'Vị trí:\s*([^\n]+)'
    match = re.search(pattern, body_text)
    if match:
        location = match.group(1).strip()
        return location
    return None


def parse_verification_link_from_body(body_text: str, body_html: str = "") -> Optional[str]:
    """Parse link xác minh từ body_text hoặc body_html của email cảnh báo"""
    # Tìm trong body_html trước (chính xác hơn)
    if body_html:
        # Tìm URL pattern: vn.shp.ee/dlink/...
        pattern = r'https?://vn\.shp\.ee/dlink/[^\s"\'<>]+'
        match = re.search(pattern, body_html)
        if match:
            return match.group(0)
        
        # Hoặc tìm trong href
        pattern = r'href=["\'](https?://vn\.shp\.ee/dlink/[^"\']+)["\']'
        match = re.search(pattern, body_html)
        if match:
            return match.group(1)
    
    # Tìm trong body_text
    if body_text:
        pattern = r'https?://vn\.shp\.ee/dlink/[^\s]+'
        match = re.search(pattern, body_text)
        if match:
            return match.group(0)
    
    return None


def parse_time_from_body(body_text: str) -> Optional[str]:
    """Parse thời gian truy cập từ body_text của email cảnh báo"""
    if not body_text:
        return None
    
    # Tìm pattern: "Thời gian truy cập: ..."
    pattern = r'Thời gian truy cập:\s*([^\n]+)'
    match = re.search(pattern, body_text)
    if match:
        time_str = match.group(1).strip()
        return time_str
    return None


def parse_shopee_otp_from_body(body_text: str) -> Optional[str]:
    """
    Trích mã OTP 6 số từ email Shopee (xác minh tài khoản).
    """
    if not body_text:
        return None
    # Dòng sau: "Mã xác minh tài khoản Shopee của bạn là:"
    m = re.search(
        r"Mã xác minh tài khoản Shopee của bạn là:\s*\n\s*(\d{6})\b",
        body_text,
        re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return m.group(1)
    # Cùng dòng với dấu hai chấm
    m = re.search(
        r"Mã xác minh tài khoản Shopee của bạn là:\s*(\d{6})\b",
        body_text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    # Tiếng Anh / biến thể ngắn
    m = re.search(
        r"(?:verification|OTP)\s+code\s+is:?\s*\n\s*(\d{6})\b",
        body_text,
        re.IGNORECASE | re.MULTILINE,
    )
    if m:
        return m.group(1)
    return None


def _is_shopee_otp_email(email: Dict[str, Any]) -> bool:
    """Email OTP Shopee: có mã trong body hoặc gửi từ Shopee + tiêu đề OTP."""
    subject = (email.get("subject") or "").lower()
    from_addr = (email.get("from_addr") or "").lower()
    body_text = email.get("body_text") or ""
    if parse_shopee_otp_from_body(body_text):
        return True
    shopee_sender = "mail.shopee" in from_addr or "shopee.vn" in from_addr
    otp_subject = (
        "mã otp" in subject
        or " otp " in f" {subject} "
        or subject.endswith(" otp")
        or subject.startswith("otp ")
        or ("otp" in subject and "shopee" in subject)
    )
    return bool(shopee_sender and otp_subject)


def get_email_type_info(email: Dict[str, Any]) -> Dict[str, Any]:
    """Xác định loại email và icon tương ứng"""
    subject = email.get('subject', '').lower()
    from_addr = email.get('from_addr', '').lower()
    
    if 'cảnh báo' in subject or 'bảo mật' in subject or 'security' in from_addr:
        return {
            'type': 'login_warning',
            'icon': '🔒',
            'title': 'Cảnh báo đăng nhập'
        }
    elif _is_shopee_otp_email(email):
        return {
            'type': 'shopee_otp',
            'icon': '🔑',
            'title': email.get('subject', 'Mã OTP Shopee'),
        }
    elif 'xác nhận' in subject or 'confirm' in subject.lower():
        return {
            'type': 'email_confirmation',
            'icon': '📧',
            'title': email.get('subject', 'Xác nhận email')
        }
    elif 'welcome' in subject.lower():
        return {
            'type': 'welcome',
            'icon': '🎉',
            'title': email.get('subject', 'Welcome')
        }
    else:
        return {
            'type': 'other',
            'icon': '📨',
            'title': email.get('subject', 'Email')
        }


def format_email_display_for_bot(idx: int, email: Dict[str, Any]) -> str:
    """Format email theo format trong hình"""
    email_type_info = get_email_type_info(email)
    icon = email_type_info['icon']
    
    # Lấy title từ subject gốc, nhưng có thể override cho login warning
    if email_type_info['type'] == 'login_warning':
        title = 'Cảnh báo đăng nhập'
    else:
        title = email.get('subject', 'Email')
        # Loại bỏ các emoji/icon có sẵn trong title để tránh duplicate
        title = re.sub(r'[🎉🔒📧📨🔑]+\s*', '', title).strip()
    
    # Format timestamp
    timestamp = format_timestamp_for_email(email.get('date', ''))
    
    # Shopee OTP: 🔑 tiêu đề | 📟 mã | ⏰ giờ + gạch ngăn
    if email_type_info['type'] == 'shopee_otp':
        body_text = email.get('body_text', '') or ''
        otp = parse_shopee_otp_from_body(body_text)
        title_show = re.sub(r'^(Shopee:\s*)', '', title, flags=re.IGNORECASE).strip() or title
        title_esc = html.escape(title_show)
        sep = "━━━━━━━━━━━━━━━━━━━━━━━━"
        if otp:
            otp_line = f"   📟 <code>{html.escape(otp)}</code>"
        else:
            otp_line = "   📟 <i>Không đọc được mã</i>"
        return (
            f"🔑 <b>{idx}. {title_esc}</b>\n"
            f"{otp_line}\n"
            f"   ⏰ {html.escape(timestamp)}\n"
            f"{sep}"
        )
    
    # Lấy thông tin device, vị trí hoặc from address; giờ xuống dòng với ⏰
    if email_type_info['type'] == 'login_warning':
        body_text = email.get('body_text', '')
        device = parse_device_from_body(body_text)
        location = parse_location_from_body(body_text)
        parts = []
        if device:
            parts.append(device)
        if location:
            parts.append(f"📍 {location}")
        line = " | ".join(parts) if parts else ""
        time_line = f"   ⏰ {timestamp}"
        if line:
            return f"{idx}. {icon} {title}\n   {line}\n{time_line}"
        return f"{idx}. {icon} {title}\n{time_line}"
    else:
        from_addr = email.get('from_addr', 'N/A')
        return f"{idx}. {icon} {title}\n   {from_addr}\n   ⏰ {timestamp}"


def get_emails_from_tempmail(email: str, password: str) -> Dict[str, Any]:
    """
    Gọi API TempMail để lấy danh sách email
    
    Args:
        email: Email address
        password: Password
        
    Returns:
        Dict với keys:
            - status: "success" hoặc "error"
            - emails: List các email (nếu success)
            - error: Error message (nếu error)
    """
    try:
        # Headers cho API request
        headers = {
            'accept': '*/*',
            'accept-language': 'vi,en-US;q=0.9,en;q=0.8',
            'content-type': 'application/json',
            'origin': 'https://cheapluxurymail.xyz',
            'priority': 'u=1, i',
            'referer': 'https://cheapluxurymail.xyz/docs',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        }
        
        json_data = {
            'email': email,
            'password': password,
        }
        
        # Gọi API
        response = requests.post(
            'https://cheapluxurymail.xyz/login',
            headers=headers,
            json=json_data,
            timeout=30
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "error": f"API trả về status code: {response.status_code}"
            }
        
        result = response.json()
        
        # Kiểm tra response
        if not isinstance(result, dict) or result.get('response_code') != 200:
            return {
                "status": "error",
                "error": result.get('message', 'Đăng nhập thất bại')
            }
        
        # Lấy danh sách email
        emails = result.get('data', {}).get('emails', [])
        
        return {
            "status": "success",
            "emails": emails
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error": f"Lỗi khi gọi API: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def create_email_buttons(emails_count: int, job_id: str) -> List[List]:
    """
    Tạo inline keyboard buttons cho danh sách email
    
    Args:
        emails_count: Số lượng email
        job_id: Job ID để lưu vào callback_data
        
    Returns:
        List các hàng buttons
    """
    buttons = []
    
    # Tạo buttons theo hàng, mỗi hàng 3 buttons
    row = []
    for i in range(1, emails_count + 1):
        row.append({
            "text": f"Thư {i}",
            "callback_data": f"email_detail_{job_id}_{i}"
        })
        
        # Mỗi hàng có 3 buttons
        if len(row) == 3:
            buttons.append(row)
            row = []
    
    # Thêm hàng cuối nếu còn buttons
    if row:
        buttons.append(row)
    
    # Thêm button "Làm mới" và "Thông tin"
    buttons.append([
        {"text": "🔄 Làm mới", "callback_data": f"email_refresh_{job_id}"},
        {"text": "ℹ️ Thông tin", "callback_data": f"email_info_{job_id}"}
    ])
    
    return buttons


def format_email_detail(email: Dict[str, Any]) -> str:
    """
    Format chi tiết một email để hiển thị
    
    Args:
        email: Email dictionary
        
    Returns:
        Message HTML với chi tiết email
    """
    email_type_info = get_email_type_info(email)
    icon = email_type_info['icon']
    
    body_text = email.get('body_text', '')
    body_html = email.get('body_html', '')
    
    # Format đặc biệt cho email cảnh báo đăng nhập
    if email_type_info['type'] == 'login_warning':
        # Parse thông tin từ body_text
        account = parse_account_from_body(body_text)
        device = parse_device_from_body(body_text)
        location = parse_location_from_body(body_text)
        verification_link = parse_verification_link_from_body(body_text, body_html)
        time_access = parse_time_from_body(body_text)
        
        # Format timestamp cho header
        timestamp = format_timestamp_for_email(email.get('date', ''))
        # Convert sang format dd/mm/yyyy HH:MM cho hiển thị
        try:
            if email.get('date'):
                date_str = email.get('date', '')
                if date_str.endswith('Z'):
                    date_str = date_str[:-1] + '+00:00'
                elif '+' not in date_str[-6:] and '-' not in date_str[-6:]:
                    date_str = date_str + '+00:00'
                dt = datetime.fromisoformat(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                vietnam_tz = timezone(timedelta(hours=7))
                dt_vietnam = dt.astimezone(vietnam_tz)
                date_formatted = dt_vietnam.strftime('%d/%m/%Y %H:%M')
            else:
                date_formatted = timestamp
        except:
            date_formatted = timestamp
        
        # Format message theo form trong hình
        message = "🔒 <b>CẢNH BÁO BẢO MẬT SHOPEE</b>\n"
        message += f"📅 {date_formatted}\n"
        message += "─" * 20 + "\n\n"
        
        # Thông tin tài khoản
        if account:
            message += f"👤 <b>Tài khoản:</b> <code>{account}</code>\n"
        
        # Thời gian
        if time_access:
            message += f"🕐 <b>Thời gian:</b> {time_access}\n"
        else:
            message += f"🕐 <b>Thời gian:</b> {date_formatted}\n"
        
        # Thiết bị
        if device:
            message += f"💻 <b>Thiết bị:</b> {device}\n"
        
        # Vị trí
        if location:
            message += f"📍 <b>Vị trí:</b> {location}\n"
        
        # Link xác minh
        if verification_link:
            message += f"🔗 <b>Link xác minh:</b> <code>{verification_link}</code>\n"
        
        return message
    
    if email_type_info['type'] == 'shopee_otp':
        otp = parse_shopee_otp_from_body(body_text)
        title = email.get('subject', 'Email')
        title = re.sub(r'[🎉🔒📧📨🔑]+\s*', '', title).strip()
        title = re.sub(r'^(Shopee:\s*)', '', title, flags=re.IGNORECASE).strip() or title
        title_esc = html.escape(title)
        timestamp = format_timestamp_for_email(email.get('date', ''))
        otp_line = (
            f"📟 <code>{html.escape(otp)}</code>"
            if otp
            else "📟 <i>Không đọc được mã</i>"
        )
        message = (
            f"🔑 <b>{title_esc}</b>\n"
            f"{otp_line}\n"
            f"⏰ {html.escape(timestamp)}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        from_addr = email.get('from_addr', 'N/A')
        to_addr = email.get('to_addr', 'N/A')
        size = email.get('size', 0)
        has_attachments = email.get('has_attachments', False)
        if size > 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.2f} MB"
        elif size > 1024:
            size_str = f"{size / 1024:.2f} KB"
        else:
            size_str = f"{size} bytes"
        message += f"📧 <b>CHI TIẾT EMAIL:</b>\n\n"
        message += f"📨 <b>Từ:</b> <code>{html.escape(str(from_addr))}</code>\n"
        message += f"📬 <b>Đến:</b> <code>{html.escape(str(to_addr))}</code>\n"
        message += f"🕐 <b>Thời gian:</b> {html.escape(timestamp)}\n"
        message += f"📏 <b>Kích thước:</b> {html.escape(size_str)}\n"
        if has_attachments:
            message += f"📎 <b>Có đính kèm:</b> Có\n"
        message += f"\n📄 <b>Nội dung:</b>\n"
        max_body_length = 3500
        if body_text:
            preview_text = body_text[:max_body_length]
            if len(body_text) > max_body_length:
                preview_text += "\n\n... (nội dung bị cắt)"
            preview_text = preview_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            message += f"<pre>{preview_text}</pre>"
        else:
            message += "Không có nội dung text."
        if len(message) > 4096:
            message = message[:4000] + "\n\n... (nội dung quá dài, đã bị cắt)"
        return message
    
    # Format cho các loại email khác
    title = email.get('subject', 'Email')
    title = re.sub(r'[🎉🔒📧📨]+\s*', '', title).strip()
    
    # Format timestamp
    timestamp = format_timestamp_for_email(email.get('date', ''))
    
    # Lấy thông tin
    from_addr = email.get('from_addr', 'N/A')
    to_addr = email.get('to_addr', 'N/A')
    size = email.get('size', 0)
    has_attachments = email.get('has_attachments', False)
    
    # Format size
    if size > 1024 * 1024:
        size_str = f"{size / (1024 * 1024):.2f} MB"
    elif size > 1024:
        size_str = f"{size / 1024:.2f} KB"
    else:
        size_str = f"{size} bytes"
    
    # Tạo message HTML
    message = f"📧 <b>CHI TIẾT EMAIL:</b>\n\n"
    message += f"{icon} <b>{title}</b>\n\n"
    message += f"📨 <b>Từ:</b> <code>{from_addr}</code>\n"
    message += f"📬 <b>Đến:</b> <code>{to_addr}</code>\n"
    message += f"🕐 <b>Thời gian:</b> {timestamp}\n"
    message += f"📏 <b>Kích thước:</b> {size_str}\n"
    
    if has_attachments:
        message += f"📎 <b>Có đính kèm:</b> Có\n"
    
    message += f"\n📄 <b>Nội dung:</b>\n"
    
    # Hiển thị body_text (giới hạn để tránh message quá dài - Telegram giới hạn 4096 ký tự)
    max_body_length = 3500
    if body_text:
        preview_text = body_text[:max_body_length]
        if len(body_text) > max_body_length:
            preview_text += "\n\n... (nội dung bị cắt)"
        # Escape HTML special characters
        preview_text = preview_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        message += f"<pre>{preview_text}</pre>"
    else:
        message += "Không có nội dung text."
    
    # Đảm bảo message không quá 4096 ký tự (giới hạn của Telegram)
    if len(message) > 4096:
        # Cắt message và thêm thông báo
        message = message[:4000] + "\n\n... (nội dung quá dài, đã bị cắt)"
    
    return message


def format_emails_list(emails: List[Dict[str, Any]]) -> str:
    """
    Format danh sách email thành message HTML cho bot
    Sắp xếp từ mới đến cũ (email mới nhất ở đầu)
    
    Args:
        emails: List các email dictionaries
        
    Returns:
        Message HTML đã format
    """
    if not emails:
        return "📭 Không có email nào trong hộp thư."
    
    # Sắp xếp email theo date từ mới đến cũ
    def get_email_date(email: Dict[str, Any]) -> datetime:
        """Lấy datetime từ email để sắp xếp"""
        date_str = email.get('date', '')
        if not date_str:
            return datetime.min.replace(tzinfo=timezone.utc)
        
        try:
            # Parse ISO string
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
    
    # Sắp xếp từ mới đến cũ (reverse=True: mới nhất trước)
    emails_sorted = sorted(emails, key=get_email_date, reverse=True)
    
    # Format danh sách email
    email_list = []
    for idx, email_item in enumerate(emails_sorted, 1):
        formatted = format_email_display_for_bot(idx, email_item)
        email_list.append(formatted)
    
    # Tạo message
    message = "📧 <b>DANH SÁCH EMAIL:</b>\n\n" + "\n\n".join(email_list)
    
    return message


def call_verification_link(verification_link: str) -> Dict[str, Any]:
    """
    Gọi request đến link xác minh Shopee - Giả lập như user click vào link
    
    Args:
        verification_link: URL xác minh từ email
        
    Returns:
        Dict chứa kết quả request
    """
    # Sử dụng Session để giữ cookies qua các redirects
    session = requests.Session()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Referer': 'https://shopee.vn/',
    }
    
    try:
        # Bước 1: Gọi GET request đến link xác minh
        response = session.get(
            verification_link,
            headers=headers,
            allow_redirects=True,
            timeout=30
        )
        
        final_url = response.url
        status_code = response.status_code
        redirect_count = len(response.history)
        
        # Bước 2: Parse HTML để tìm form và submit nếu có
        html_content = response.text
        
        # Tìm form trong HTML
        form_action = None
        form_method = 'GET'
        form_data = {}
        
        # Tìm form action
        form_action_match = re.search(r'<form[^>]*action=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if form_action_match:
            form_action = form_action_match.group(1)
            # Nếu là relative URL, convert sang absolute
            if form_action.startswith('/'):
                from urllib.parse import urljoin
                form_action = urljoin(final_url, form_action)
        
        # Tìm form method
        form_method_match = re.search(r'<form[^>]*method=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if form_method_match:
            form_method = form_method_match.group(1).upper()
        
        # Tìm các input hidden trong form
        input_matches = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']', html_content, re.IGNORECASE)
        for name, value in input_matches:
            form_data[name] = value
        
        # Tìm button submit
        submit_button_match = re.search(r'<button[^>]*type=["\']submit["\'][^>]*name=["\']([^"\']+)["\']', html_content, re.IGNORECASE)
        if submit_button_match:
            form_data[submit_button_match.group(1)] = ''
        
        # Biến để lưu response cuối cùng
        last_response = response
        
        # Bước 3: Submit form nếu tìm thấy
        if form_action and form_method:
            # Update referer
            headers['Referer'] = final_url
            
            if form_method == 'POST':
                # Submit POST form
                form_response = session.post(
                    form_action,
                    data=form_data,
                    headers=headers,
                    allow_redirects=True,
                    timeout=30
                )
                final_url = form_response.url
                status_code = form_response.status_code
                redirect_count += len(form_response.history)
                last_response = form_response
            else:
                # Submit GET form
                from urllib.parse import urlencode
                if form_data:
                    query_string = urlencode(form_data)
                    form_url = f"{form_action}?{query_string}" if '?' not in form_action else f"{form_action}&{query_string}"
                else:
                    form_url = form_action
                
                form_response = session.get(
                    form_url,
                    headers=headers,
                    allow_redirects=True,
                    timeout=30
                )
                final_url = form_response.url
                status_code = form_response.status_code
                redirect_count += len(form_response.history)
                last_response = form_response
        
        # Bước 4: Kiểm tra JavaScript và meta refresh redirects (tối đa 5 lần để tránh vòng lặp)
        max_redirect_attempts = 5
        redirect_attempts = 0
        
        while redirect_attempts < max_redirect_attempts:
            current_html = last_response.text
            found_redirect = False
            
            # Kiểm tra JavaScript redirect
            js_redirect_match = re.search(r'window\.location\s*=\s*["\']([^"\']+)["\']', current_html, re.IGNORECASE)
            if js_redirect_match:
                redirect_url = js_redirect_match.group(1)
                # Convert relative URL sang absolute
                if redirect_url.startswith('/') or not redirect_url.startswith('http'):
                    from urllib.parse import urljoin
                    redirect_url = urljoin(final_url, redirect_url)
                
                # Follow JavaScript redirect
                js_response = session.get(
                    redirect_url,
                    headers=headers,
                    allow_redirects=True,
                    timeout=30
                )
                final_url = js_response.url
                status_code = js_response.status_code
                redirect_count += len(js_response.history)
                last_response = js_response
                found_redirect = True
                redirect_attempts += 1
                continue
            
            # Kiểm tra meta refresh redirect
            meta_refresh_match = re.search(r'<meta[^>]*http-equiv=["\']refresh["\'][^>]*content=["\']\d+;\s*url=([^"\']+)["\']', current_html, re.IGNORECASE)
            if meta_refresh_match:
                refresh_url = meta_refresh_match.group(1)
                if refresh_url.startswith('/') or not refresh_url.startswith('http'):
                    from urllib.parse import urljoin
                    refresh_url = urljoin(final_url, refresh_url)
                
                meta_response = session.get(
                    refresh_url,
                    headers=headers,
                    allow_redirects=True,
                    timeout=30
                )
                final_url = meta_response.url
                status_code = meta_response.status_code
                redirect_count += len(meta_response.history)
                last_response = meta_response
                found_redirect = True
                redirect_attempts += 1
                continue
            
            # Không tìm thấy redirect nào, thoát khỏi vòng lặp
            break
        
        # Bước 5: Tìm và click button/link xác minh trong trang sau khi redirect
        # Sau khi redirect đến trang xác minh, cần tìm button/link để click tiếp
        verification_button_clicked = False
        max_button_click_attempts = 3
        button_click_attempts = 0
        
        while button_click_attempts < max_button_click_attempts:
            current_html = last_response.text
            verification_url = None
            
            # Tìm các pattern button/link xác minh
            # Pattern 1: Button với text chứa "xác minh", "verify", "confirm", "xác nhận"
            button_patterns = [
                r'<button[^>]*>.*?(?:xác\s*minh|verify|confirm|xác\s*nhận|tiếp\s*tục|continue)[^<]*</button>',
                r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>.*?(?:xác\s*minh|verify|confirm|xác\s*nhận|tiếp\s*tục|continue)[^<]*</a>',
                r'<input[^>]*type=["\'](?:submit|button)["\'][^>]*value=["\']([^"\']*(?:xác\s*minh|verify|confirm|xác\s*nhận|tiếp\s*tục|continue)[^"\']*)["\']',
            ]
            
            # Tìm form có button xác minh
            # Tìm tất cả các form trong HTML
            form_matches = re.finditer(
                r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>(.*?)</form>',
                current_html,
                re.IGNORECASE | re.DOTALL
            )
            
            for form_match in form_matches:
                form_action_url = form_match.group(1)
                form_content = form_match.group(2)
                
                # Kiểm tra xem form có chứa button/link xác minh không
                verification_keywords = ['xác minh', 'verify', 'confirm', 'xác nhận', 'tiếp tục', 'continue']
                has_verification_button = any(
                    keyword in form_content.lower() 
                    for keyword in verification_keywords
                )
                
                if has_verification_button:
                    # Convert relative URL sang absolute
                    if form_action_url.startswith('/') or not form_action_url.startswith('http'):
                        from urllib.parse import urljoin
                        form_action_url = urljoin(final_url, form_action_url)
                    
                    # Parse form data (tất cả inputs, không chỉ hidden)
                    form_data_for_button = {}
                    
                    # Lấy tất cả inputs trong form
                    input_matches = re.findall(
                        r'<input[^>]*name=["\']([^"\']+)["\'][^>]*(?:value=["\']([^"\']*)["\'])?',
                        form_content,
                        re.IGNORECASE
                    )
                    for name, value in input_matches:
                        if value:
                            form_data_for_button[name] = value
                        else:
                            # Nếu không có value, để empty string
                            form_data_for_button[name] = ''
                    
                    # Tìm method của form (mặc định là GET)
                    form_method_match = re.search(
                        r'method=["\']([^"\']+)["\']',
                        form_match.group(0),
                        re.IGNORECASE
                    )
                    form_method = form_method_match.group(1).upper() if form_method_match else 'GET'
                    
                    # Submit form
                    headers['Referer'] = final_url
                    if form_method == 'POST':
                        button_response = session.post(
                            form_action_url,
                            data=form_data_for_button,
                            headers=headers,
                            allow_redirects=True,
                            timeout=30
                        )
                    else:
                        from urllib.parse import urlencode
                        if form_data_for_button:
                            query_string = urlencode(form_data_for_button)
                            form_url = f"{form_action_url}?{query_string}" if '?' not in form_action_url else f"{form_action_url}&{query_string}"
                        else:
                            form_url = form_action_url
                        button_response = session.get(
                            form_url,
                            headers=headers,
                            allow_redirects=True,
                            timeout=30
                        )
                    
                    final_url = button_response.url
                    status_code = button_response.status_code
                    redirect_count += len(button_response.history)
                    last_response = button_response
                    verification_button_clicked = True
                    button_click_attempts += 1
                    break
            
            if verification_button_clicked:
                continue
            
            # Tìm link xác minh (a tag)
            link_patterns = [
                r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>.*?(?:xác\s*minh|verify|confirm|xác\s*nhận|tiếp\s*tục|continue)[^<]*</a>',
                r'<a[^>]*href=["\']([^"\']+verify[^"\']*)["\'][^>]*>',
                r'<a[^>]*href=["\']([^"\']+confirm[^"\']*)["\'][^>]*>',
            ]
            
            for pattern in link_patterns:
                link_match = re.search(pattern, current_html, re.IGNORECASE)
                if link_match:
                    verification_url = link_match.group(1)
                    # Convert relative URL sang absolute
                    if verification_url.startswith('/') or not verification_url.startswith('http'):
                        from urllib.parse import urljoin
                        verification_url = urljoin(final_url, verification_url)
                    
                    # Click vào link
                    headers['Referer'] = final_url
                    link_response = session.get(
                        verification_url,
                        headers=headers,
                        allow_redirects=True,
                        timeout=30
                    )
                    final_url = link_response.url
                    status_code = link_response.status_code
                    redirect_count += len(link_response.history)
                    last_response = link_response
                    verification_button_clicked = True
                    button_click_attempts += 1
                    break
            
            if verification_url:
                continue
            
            # Không tìm thấy button/link xác minh, thoát khỏi vòng lặp
            break
        
        # Bước 6: Gọi thêm một lần nữa đến URL cuối cùng để đảm bảo xác minh hoàn tất
        # Đặc biệt quan trọng với URL verify/email-link - cần gọi lại để hoàn tất xác minh
        if final_url and final_url != verification_link:
            try:
                # Kiểm tra xem URL có chứa verify/email-link không
                is_verify_url = 'verify/email-link' in final_url or '/dlink/verify' in final_url
                
                # Update referer
                headers['Referer'] = final_url
                
                # Gọi lại URL cuối cùng một lần nữa
                # Điều này đảm bảo rằng xác minh được hoàn tất, đặc biệt với verify/email-link
                final_call_response = session.get(
                    final_url,
                    headers=headers,
                    allow_redirects=True,
                    timeout=30
                )
                
                # Cập nhật thông tin từ response cuối cùng
                previous_url = final_url
                final_url = final_call_response.url
                status_code = final_call_response.status_code
                redirect_count += len(final_call_response.history)
                last_response = final_call_response
                
                # Nếu là verify URL, luôn gọi thêm một lần nữa để đảm bảo xác minh hoàn tất
                if is_verify_url:
                    # Gọi lại verify URL một lần nữa để hoàn tất xác minh
                    headers['Referer'] = final_url
                    second_call_response = session.get(
                        final_url,
                        headers=headers,
                        allow_redirects=True,
                        timeout=30
                    )
                    final_url = second_call_response.url
                    status_code = second_call_response.status_code
                    redirect_count += len(second_call_response.history)
                    last_response = second_call_response
            except Exception as e:
                # Nếu có lỗi khi gọi lại, vẫn sử dụng response trước đó
                pass
        
        # Kiểm tra kết quả cuối cùng từ response cuối cùng
        success_indicators = [
            'xác minh thành công',
            'verification successful',
            'đã xác minh',
            'verified',
            'success',
            'thành công'
        ]
        
        # Lấy HTML từ response cuối cùng
        final_html = last_response.text.lower()
        is_success = any(indicator in final_html for indicator in success_indicators)
        
        return {
            "status": "success",
            "http_status": status_code,
            "url": final_url,
            "redirected": redirect_count > 0,
            "redirect_count": redirect_count,
            "form_submitted": form_action is not None,
            "verification_button_clicked": verification_button_clicked,
            "is_success": is_success,
            "message": f"Đã giả lập click thành công. Status: {status_code}. {'Đã click button xác minh. ' if verification_button_clicked else ''}{'Có vẻ như xác minh thành công!' if is_success else 'Đã xử lý xong.'}"
        }
        
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error": "Request timeout - Link không phản hồi trong 30 giây"
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "error": "Lỗi kết nối - Không thể kết nối đến server"
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error": f"Lỗi request: {str(e)}"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Lỗi không xác định: {str(e)}"
        }

def extract_spc_st_cookie(cookie: str) -> str:
    raw = (cookie or "").strip()
    if not raw:
        return ""

    if ";" in raw:
        for part in raw.split(";"):
            item = part.strip()
            if item.startswith("SPC_ST="):
                return item
        return ""

    if raw.startswith("SPC_ST="):
        return raw

    return f"SPC_ST={raw}"


def api_add_email_by_cookie(cookie: str, email: str, proxies: dict | None = None) -> dict:
    cookie = (cookie or "").strip()
    email = (email or "").strip()
    if not cookie or not email:
        return {
            "success": False,
            "message": "Thieu cookie hoac email",
            "username": None,
            "phone": None,
            "email": None,
        }

    session = requests.Session()
    if proxies:
        session.proxies.update(proxies)
    st_cookie = extract_spc_st_cookie(cookie)
    if not st_cookie:
        return {
            "success": False,
            "message": "Cookie khong chua SPC_ST",
            "username": None,
            "phone": None,
            "email": None,
        }

    headers_get = {
        "accept": "application/json, text/plain, */*",
        "cookie": st_cookie,
        "user-agent": "Mozilla/5.0",
    }

    try:
        resp = session.get(
            "https://banhang.shopee.vn",
            headers=headers_get,
            timeout=(5, 20),
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": f"Loi ket noi: {exc}",
            "username": None,
            "phone": None,
            "email": None,
        }

    spc_sc_session = resp.cookies.get("SPC_SC_SESSION")
    if not spc_sc_session:
        return {
            "success": False,
            "message": "Cookie die hoac het han",
            "username": None,
            "phone": None,
            "email": None,
        }

    def _auth_cookie() -> str:
        return f"{st_cookie}; SPC_SC_SESSION={spc_sc_session}"

    def get_account_info() -> dict:
        url = "https://shopee.vn/api/v4/account/basic/get_account_info"
        headers = {"cookie": _auth_cookie(), "user-agent": "Mozilla/5.0"}
        try:
            r = session.get(url, headers=headers, timeout=(5, 20))
            return (r.json() or {}).get("data") or {}
        except Exception:
            return {}

    info_before = get_account_info()
    if info_before.get("email"):
        return {
            "success": False,
            "message": f"Tai khoan da co email: {info_before.get('email')}",
            "username": info_before.get("username"),
            "phone": info_before.get("phone"),
            "email": info_before.get("email"),
        }

    url_post = (
        "https://banhang.shopee.vn/api/onboarding/local_onboard/v1/"
        "vn_onboard/save/?SPC_CDS=1fe0f0ea-5d75-4ba4-a530-5bae262fe0ef&SPC_CDS_VER=2"
    )
    payload = {
        "check": False,
        "lang": "vi",
        "step": {
            "step_id": 291100,
            "form": {
                "form_version": 1,
                "save_version": 0,
                "form_id": 291100,
                "components": [
                    {"component_id_str": "form_0_component_291103_c", "component_value": email}
                ],
            },
        },
    }
    headers_post = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "cookie": _auth_cookie(),
        "origin": "https://banhang.shopee.vn",
        "referer": "https://banhang.shopee.vn/portal/vn-onboarding/form/291000/291100",
        "user-agent": "Mozilla/5.0",
    }

    try:
        session.post(url_post, headers=headers_post, json=payload, timeout=(5, 20))
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": f"Loi gui form them email: {exc}",
            "username": None,
            "phone": None,
            "email": None,
        }

    time.sleep(1)
    info_after = get_account_info()
    updated_email = info_after.get("email")

    if updated_email == email:
        return {
            "success": True,
            "message": f"Them email thanh cong: {email}",
            "username": info_after.get("username"),
            "phone": info_after.get("phone"),
            "email": updated_email,
        }

    return {
        "success": False,
        "message": "Them email that bai",
        "username": info_after.get("username"),
        "phone": info_after.get("phone"),
        "email": updated_email,
    }


def api_change_email_by_cookie(cookie: str, email: str, proxies: dict | None = None) -> dict:
    cookie = (cookie or "").strip()
    email = (email or "").strip()
    if not cookie or not email:
        return {
            "success": False,
            "message": "Thieu cookie hoac email",
            "username": None,
            "phone": None,
            "email": None,
        }

    session = requests.Session()
    if proxies:
        session.proxies.update(proxies)
    st_cookie = extract_spc_st_cookie(cookie)
    if not st_cookie:
        return {
            "success": False,
            "message": "Cookie khong chua SPC_ST",
            "username": None,
            "phone": None,
            "email": None,
        }

    headers_get = {
        "accept": "application/json, text/plain, */*",
        "cookie": st_cookie,
        "user-agent": "Mozilla/5.0",
    }

    try:
        resp = session.get(
            "https://banhang.shopee.vn",
            headers=headers_get,
            timeout=(5, 20),
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": f"Loi ket noi: {exc}",
            "username": None,
            "phone": None,
            "email": None,
        }

    spc_sc_session = resp.cookies.get("SPC_SC_SESSION")
    if not spc_sc_session:
        return {
            "success": False,
            "message": "Cookie die hoac het han",
            "username": None,
            "phone": None,
            "email": None,
        }

    def _auth_cookie() -> str:
        return f"{st_cookie}; SPC_SC_SESSION={spc_sc_session}"

    def get_account_info() -> dict:
        url = "https://shopee.vn/api/v4/account/basic/get_account_info"
        headers = {"cookie": _auth_cookie(), "user-agent": "Mozilla/5.0"}
        try:
            r = session.get(url, headers=headers, timeout=(5, 20))
            return (r.json() or {}).get("data") or {}
        except Exception:
            return {}

    info_before = get_account_info()
    print(f"info_before:{info_before}")
    # if info_before.get("email"):
    #     print(f"info_before:{info_before}")
    #     return {
    #         "success": False,
    #         "message": f"Tai khoan da co email: {info_before.get('email')}",
    #         "username": info_before.get("username"),
    #         "phone": info_before.get("phone"),
    #         "email": info_before.get("email"),
    #     }

    url_post = (
        "https://banhang.shopee.vn/api/onboarding/local_onboard/v1/"
        "vn_onboard/save/?SPC_CDS=1fe0f0ea-5d75-4ba4-a530-5bae262fe0ef&SPC_CDS_VER=2"
    )
    payload = {
        "check": False,
        "lang": "vi",
        "step": {
            "step_id": 291100,
            "form": {
                "form_version": 1,
                "save_version": 0,
                "form_id": 291100,
                "components": [
                    {"component_id_str": "form_0_component_291103_c", "component_value": email}
                ],
            },
        },
    }
    headers_post = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "cookie": _auth_cookie(),
        "origin": "https://banhang.shopee.vn",
        "referer": "https://banhang.shopee.vn/portal/vn-onboarding/form/291000/291100",
        "user-agent": "Mozilla/5.0",
    }

    try:
        session.post(url_post, headers=headers_post, json=payload, timeout=(5, 20))
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": f"Loi gui form them email: {exc}",
            "username": None,
            "phone": None,
            "email": None,
        }

    time.sleep(1)
    info_after = get_account_info()
    updated_email = info_after.get("email")

    if updated_email == email:
        return {
            "success": True,
            "message": f"Them email thanh cong: {email}",
            "username": info_after.get("username"),
            "phone": info_after.get("phone"),
            "email": updated_email,
        }

    return {
        "success": False,
        "message": "Them email that bai",
        "username": info_after.get("username"),
        "phone": info_after.get("phone"),
        "email": updated_email,
    }

def process_mailfree(
    raw_input: str,
    proxies: Dict[str, str],
) -> Dict[str, Any]:
    """
    Xử lý logic cho /mailfree.

    Input hỗ trợ 2 dạng:
      1) SPC_ST=... (cookie)
      2) id|pass|spc_f (hoặc id|pass||spc_f) để extract SPC_ST trước
    """
    raw = (raw_input or "").strip()

    # Tạo email free (random local_part + password) (dùng proxy)
    email, email_password, reg_result = api.register_email_full("", "", proxies=proxies)
    if not email or not email_password:
        return {
            "status": "success",
            "message": "❌ Không tạo được email free",
            "message_format": "HTML",
            "debug": reg_result,
        }

    # Dạng 1: có SPC_ST
    add_result: Dict[str, Any]
    if "SPC_ST=" in raw and "|" not in raw:
        add_result = api_add_email_by_cookie(cookie=raw, email=email, proxies=proxies)
    else:
        # Dạng 2: id|pass|spc_f -> convert về format login.parse_input đang nhận
        parts = [p.strip() for p in raw.split("|")]
        input_line = raw
        if len(parts) == 4:
            username, password, sdt, spc_f = parts
            input_line = f"{username}|{password}||{spc_f}"

        try:
            import login as login_mod

            spc_st = login_mod.extract_spc_st(input_line, proxies=proxies)
        except Exception as e:
            return {"status": "error", "error": f"Extract SPC_ST thất bại: {e}"}

        add_result = api_add_email_by_cookie(cookie=spc_st, email=email, proxies=proxies)

    success = bool(add_result.get("success"))
    msg = (
        "✅ <b>Bạn đã thêm MAILFREE thành công</b>\n\n"
        f"📧 Email: <code>{email}</code>\n"
        f"🔑 Password: <code>{email_password}</code>\n"
        f"🔑 Email|Password: <code>{email}|{email_password}</code>\n\n"
    )
    if add_result.get("username"):
        msg += f"• Username: <code>{add_result.get('username')}</code>\n"
    if add_result.get("phone"):
        msg += f"• Phone: <code>{add_result.get('phone')}</code>\n"

    return {
        "status": "success" if success else "error",
        "message": msg,
        "message_format": "HTML",
        # Trả thêm creds để worker/commands có thể tạo nút "Đọc email"
        "email": email,
        "password": email_password,
    }

cookie = "SPC_ST=cUJseVdjeG1kNUJXSElMZS8Yc8SUP7Sg9Hm11/jo+M61g/dNFxCNS9nbEThir8FgEx1qTTzFlkaz7kLue7SLXivIS+OcSKnylcjdNp2odNK3khZUYWwpa1m8b57e+94Y0AH5cNYH/Bhd3uivpSZ8OUX+smNmKolf+c32zt17nw5cvy9CW44rI8dKFiGnaoR1LI482bvkRBS065EPc/7E6NKvJAa2YMHYw6n4p4Bs0WY=.AKTqhphS/HCc31MQ3kgP6pmWHPAr8viWnPrwpY6IrKk9"
value = api_change_email_by_cookie(cookie=cookie, email="7c0jvmgxu6@namkhanh61.com", proxies=None)
print(f"value:{value}")
