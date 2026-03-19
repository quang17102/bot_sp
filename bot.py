# -*- coding: utf-8 -*-
import hashlib
import json
from math import e
import secrets
import sys
from typing import Dict, Iterable, Optional
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
def generate_random_fingerprint() -> str:
    return secrets.token_hex(16)


def generate_random_csrf_token() -> str:
    return secrets.token_hex(16)

def generate_random_user_agent() -> str:
    chrome_major = 120 + secrets.randbelow(8)
    chrome_build = 6000 + secrets.randbelow(600)
    chrome_patch = 100 + secrets.randbelow(200)
    chrome_version = f"{chrome_major}.0.{chrome_build}.{chrome_patch}"
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_version} Safari/537.36"
    )


def parse_input(raw: str) -> tuple[str, str, str, str]:
    if not raw or not raw.strip():
        raise ValueError(
            'Thi\u1ebfu input. D\u00f9ng: python xuatspc_st.py "SPC_F=...|username|password"'
        )

    parts = [part.strip() for part in raw.split("|")]
    if len(parts) < 3:
        raise ValueError("\u0110\u1ecbnh d\u1ea1ng kh\u00f4ng h\u1ee3p l\u1ec7. C\u1ea7n: SPC_F=value|username|password")

    username, password, sdt ,spc_f_part, = parts[:4]
    if not spc_f_part or not username or not password:
        raise ValueError("Thi\u1ebfu SPC_F, username ho\u1eb7c password")

    if spc_f_part.startswith("SPC_F="):
        spc_f_part = spc_f_part[6:]

    if not spc_f_part:
        raise ValueError("SPC_F kh\u00f4ng h\u1ee3p l\u1ec7")

    return spc_f_part, username, password


def collect_cookies_from_response(response: requests.Response) -> Dict[str, str]:
    cookie_map: Dict[str, str] = {}
    raw_headers = response.raw.headers
    set_cookie_headers: Iterable[str] = raw_headers.get_all("Set-Cookie") or []

    for cookie_header in set_cookie_headers:
        pair = cookie_header.split(";", 1)[0]
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookie_map[name] = value

    return cookie_map


def extract_spc_st_from_response(response: requests.Response) -> Optional[str]:
    raw_headers = response.raw.headers
    set_cookie_headers: Iterable[str] = raw_headers.get_all("Set-Cookie") or []

    for cookie_header in set_cookie_headers:
        pair = cookie_header.split(";", 1)[0]
        if not pair.startswith("SPC_ST="):
            continue
        return pair.split("=", 1)[1]

    return None


def extract_spc_st(input_line: str) -> str:
    spc_f, username, password = parse_input(input_line)
    # print(spc_f, username, password)
    md5_hash = hashlib.md5(password.encode("utf-8")).hexdigest()
    sha256_hash = hashlib.sha256(md5_hash.encode("utf-8")).hexdigest()

    url = "https://shopee.vn/api/v4/account/login_by_password"
    base_headers = {
        "Host": "shopee.vn",
        "User-Agent": generate_random_user_agent(),
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://shopee.vn/buyer/login",
        "x-csrftoken": generate_random_csrf_token(),
    }
    payload = {
        "username": username,
        "password": sha256_hash,
        "support_ivs": True,
        "client_identifier": {
            "security_device_fingerprint": generate_random_fingerprint(),
        },
    }

    session = requests.Session()

    first_res = session.post(url, headers=base_headers, json=payload, timeout=15)
    if not first_res.ok:
        raise RuntimeError(
            f"Request 1 th\u1ea5t b\u1ea1i: HTTP {first_res.status_code} {first_res.reason}"
        )

    first_cookies = collect_cookies_from_response(first_res)
    first_cookies["SPC_F"] = spc_f
    cookie_header = "; ".join(
        f"{name}={value}" for name, value in first_cookies.items()
    )

    second_headers = dict(base_headers)
    second_headers["Cookie"] = cookie_header

    second_res = session.post(url, headers=second_headers, json=payload, timeout=15)
    if not second_res.ok:
        body_preview = second_res.text[:200]
        raise RuntimeError(
            f"Request 2 th\u1ea5t b\u1ea1i: HTTP {second_res.status_code} {second_res.reason} - {body_preview}"
        )

    try:
        body = second_res.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError("Response Shopee kh\u00f4ng ph\u1ea3i JSON") from exc

    if body.get("error") != 0:
        error_message = body.get("error_msg") or f"Error code {body.get('error')}"
        raise RuntimeError(f"Login failed: {error_message}")

    spc_st = extract_spc_st_from_response(second_res)
    if not spc_st:
        raise RuntimeError("Kh\u00f4ng t\u00ecm th\u1ea5y SPC_ST trong response")

    return spc_st


def read_input() -> str:
    arg_input = " ".join(sys.argv[1:]).strip()
    if arg_input:
        return arg_input

    stdin_input = sys.stdin.read().strip()
    return stdin_input


from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8667315240:AAFj9GwaVWqYUUxGjxHQFwi9IaQodhVgjnA"
# TOKEN = "8779407961:AAEmCsWPOpjUueWc7uH8HsDhwPfVcV4hjwY"

# ch\u1ee9c n\u0103ng start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Xem s\u1ed1 d\u01b0", callback_data="balance")],
        [InlineKeyboardButton("T\u1ea1o \u0111\u01a1n", callback_data="order")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Encode message text to ensure UTF-8 compatibility
    message_text = (
        "\U0001F4DD K\u1ebeT QU\u1ea2 CHECK VOUCHER\n\n"
        "\U0001F3AB CRMNUICL80T3\n"
        "\U0001F4B0 Gi\u1ea3m: 100.000\u0111 | \u0110\u01a1n 0\u0111\n"
        "\U0001F4CA \u0110\u00e3 d\u00f9ng: 81% \U0001F7E2\n"
        "\U0001F4E5 L\u01b0\u1ee3t l\u01b0u: C\u00f2n l\u01b0\u1ee3t\n"
        "\u23F0 H\u1ea1n: 23:59:00 31/3/2026"
    )
    # Ensure proper UTF-8 encoding
    message_text = message_text.encode('utf-8', errors='replace').decode('utf-8')
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup
    )

# ch\u1ee9c n\u0103ng help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("C\u00e1c l\u1ec7nh:\n/start\n/help\n/id")

# ch\u1ee9c n\u0103ng l\u1ea5y user id
async def getcookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args   # l\u1ea5y tham s\u1ed1 sau command
    if len(args) == 0:
        await update.message.reply_text("Thi\u1ebfu tham s\u1ed1")
        return
    try:
        cookie = args[0]
        print(cookie)
        spc_st = extract_spc_st(cookie)
        print(f"SPC_ST={spc_st}")
        username = ""
        email = ""
        phone = ""
        created = ""
        # user_id = update.message.from_user.id
        # Format SPC_ST d\u1ea1ng code \u0111\u1ec3 d\u1ec5 copy
        cookie_text = f"SPC_ST={spc_st}"
        await update.message.reply_text(
            "\u2705 Nh\u1ea5n v\u00f4 Cookies \u0111\u1ec3 COPY\n\n"
            f"<code>{cookie_text}</code>\n\n"
            "<b>\U0001F4CB Th\u00f4ng Tin T\u00e0i Kho\u1ea3n:</b>\n"
            f"• Username: {username if username else 'None'}\n"
            f"• Email: {email if email else 'None'}\n"
            f"• Phone: {phone if phone else 'None'}\n"
            f"• Ng\u00e0y t\u1ea1o: {created if created else 'None'}",
            parse_mode='HTML'
        )
    except Exception as e:
        await update.message.reply_text(f"{e}")
        

async def cvc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    # user_id = update.message.from_user.id
    await update.message.reply_text(f"SPC_ST")

async def vc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args   # l\u1ea5y tham s\u1ed1 sau command
        if len(args) == 0:
            await update.message.reply_text("Thi\u1ebfu tham s\u1ed1")
            return

        cookie = args[0].split('=')
        if len(cookie) > 2:
            result = '='.join(cookie[1:])
        else:
            result = cookie[1]
        srftols = generate_random_csrf_token()
        cookies = {
            '_med': 'refer',
            'language': 'vi',
            '_gid': 'GA1.2.1962185123.1773419705',
            'csrftoken': srftols,
            'SPC_ST': result,
        }
        headers = {
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'af-ac-enc-dat': '78475526452b9fa5',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': 'https://shopee.vn',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://shopee.vn/m/ma-giam-gia',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'x-api-source': 'pc',
            'x-csrftoken': srftols,
            'x-requested-with': 'XMLHttpRequest',
            'x-shopee-language': 'vi',
            'x-sz-sdk-version': '1.12.33',
        }

        json_data = {
            'voucher_code': 'CRMNUICL80T3',
            'voucher_promotionid': 1365690377211904,
            'signature': 'b3ca10e3fa0e469b3c52577083cb3ee617ec2d40dd6ad1a3130609050d296c93',
            'signature_source': '0',
            'caller_source': 6,
        }

        response = requests.post('https://shopee.vn/api/v4/microsite/save_voucher', cookies=cookies, headers=headers, json=json_data)
        body = response.json()
        print(body)
        print(body['data']['voucher']['promotionid'])
        if(body['data']['voucher']['promotionid'] == 1365690377211904):
            print("L\u01b0u m\u00e3 th\u00e0nh c\u00f4ng")
            await update.message.reply_text(f"L\u01b0u m\u00e3 100k th\u00e0nh c\u00f4ng")
        else:
            await update.message.reply_text(f"L\u01b0u m\u00e3 th\u1ea5t b\u1ea1i")
    except Exception as e:
        await update.message.reply_text(f"L\u01b0u m\u00e3 th\u1ea5t b\u1ea1i")
    # user_id = update.message.from_user.id
    
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
# app.add_handler(CommandHandler("getcookies", help_command))
app.add_handler(CommandHandler("cks", getcookies))

app.add_handler(CommandHandler("vc", vc))
app.add_handler(CommandHandler("cvc", cvc))

app.run_polling()