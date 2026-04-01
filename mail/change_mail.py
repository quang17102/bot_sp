# -*- coding: utf-8 -*-
"""Shopee change-mail helpers used by Telegram commands."""

import base64
import os
import random
import re
import string
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests

from mail.utils import get_emails_from_tempmail, parse_shopee_otp_from_body

BASE_URL = "https://mall.shopee.vn"
ProxyDict = Dict[str, str]
FINGERPRINT = (
    f"{base64.b64encode(os.urandom(16)).decode()}|"
    f"{base64.b64encode(os.urandom(64)).decode()}|"
    f"{''.join(random.choices(string.ascii_letters + string.digits, k=16))}|"
    f"{str(random.randint(1, 99)).zfill(2)}|{str(random.randint(1, 5))}"
)


def clean_spc_st(raw_input: str) -> str:
    raw_input = (raw_input or "").strip()
    if raw_input.startswith("SPC_ST="):
        return raw_input.split("SPC_ST=", 1)[1]
    if "SPC_ST=" in raw_input:
        for part in raw_input.split(";"):
            part = part.strip()
            if part.startswith("SPC_ST="):
                return part.split("SPC_ST=", 1)[1]
    return raw_input


def get_headers(spc_st: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Source": "rn",
        "User-Agent": (
            "iOS app iPhone Shopee appver=37036 language=vi app_type=1 "
            "platform=native_ios os_ver=26.3.1 Cronet/102.0.5005.61"
        ),
        "Cookie": f"SPC_ST={spc_st}",
    }


def safe_post(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    proxies: Optional[ProxyDict] = None,
) -> Optional[Dict[str, Any]]:
    try:
        kw: Dict[str, Any] = {"timeout": 15}
        if proxies:
            kw["proxies"] = proxies
        res = requests.post(url, headers=headers, json=payload, **kw)
        try:
            return res.json()
        except Exception:
            return None
    except Exception:
        return None


def _api_error(data: Optional[Dict[str, Any]]) -> Optional[str]:
    if not data:
        return "Không có phản hồi JSON từ Shopee"
    err = data.get("error")
    if err not in (None, 0):
        return str(data.get("error_msg") or data.get("error") or err)
    return None


def change_email_init(spc_st: str, proxies: Optional[ProxyDict] = None) -> Optional[str]:
    url = BASE_URL + "/api/v4/account/management/change_email_init"
    payload = {
        "client_info": {
            "identifier": {"security_device_fingerprint": FINGERPRINT}
        }
    }
    data = safe_post(url, get_headers(spc_st), payload, proxies=proxies)
    if not data:
        return None
    token = data.get("data", {}).get("change_email_token")
    if not token or _api_error(data):
        return None
    return token


def init_email_otp(
    spc_st: str,
    email: str,
    proxies: Optional[ProxyDict] = None,
) -> Optional[Dict[str, Any]]:
    url = BASE_URL + "/api/v4/otp/init_email_otp"
    payload = {
        "email": email,
        "operation": 24,
        "support_session": True,
        "client_identifier": {"security_device_fingerprint": FINGERPRINT},
    }
    return safe_post(url, get_headers(spc_st), payload, proxies=proxies)


def send_email_otp(
    spc_st: str,
    email: str,
    proxies: Optional[ProxyDict] = None,
) -> Optional[str]:
    url = BASE_URL + "/api/v4/otp/send_email_otp"
    payload = {
        "email": email,
        "operation": 24,
        "encrypted_email": "",
        "captcha_signature": "",
        "seed": "",
        "first_otp": True,
        "support_session": True,
        "client_identifier": {"security_device_fingerprint": FINGERPRINT},
    }
    data = safe_post(url, get_headers(spc_st), payload, proxies=proxies)
    if not data:
        return None
    seed = data.get("data", {}).get("session_info", {}).get("seed")
    if not seed or _api_error(data):
        return None
    return seed


def verify_email_otp(
    spc_st: str,
    email: str,
    otp: str,
    seed: str,
    proxies: Optional[ProxyDict] = None,
) -> Optional[str]:
    url = BASE_URL + "/api/v4/otp/verify_email_otp"
    payload = {
        "otp": otp,
        "operation": 24,
        "email": email,
        "encrypted_email": "",
        "seed": seed,
        "support_session": True,
        "client_identifier": {"security_device_fingerprint": FINGERPRINT},
    }
    data = safe_post(url, get_headers(spc_st), payload, proxies=proxies)
    if not data:
        return None
    token = data.get("data", {}).get("email_otp_token")
    if not token or _api_error(data):
        return None
    return token


def change_email_commit(
    spc_st: str,
    change_email_token: str,
    email: str,
    email_otp_token: str,
    proxies: Optional[ProxyDict] = None,
) -> Dict[str, Any]:
    url = BASE_URL + "/api/v4/account/management/change_email_commit"
    payload = {
        "change_email_token": change_email_token,
        "new_email": email,
        "email_otp_token": email_otp_token,
        "ivs_signature": None,
        "ivs_method": None,
        "subscribe_newsletter": True,
        "client_info": {
            "identifier": {"security_device_fingerprint": FINGERPRINT}
        },
    }
    data = safe_post(url, get_headers(spc_st), payload, proxies=proxies)
    if not data:
        return {"ok": False, "error": "Không có phản hồi JSON khi commit."}
    err = _api_error(data)
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "raw": data}


def _email_ts_unix(email: Dict[str, Any]) -> Optional[float]:
    for key in ("created_at", "date", "time", "timestamp"):
        v = email.get(key)
        if not v:
            continue
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip()
            if s.isdigit():
                return float(s)
            try:
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                return datetime.fromisoformat(s).timestamp()
            except Exception:
                continue
    return None


def _email_body_plain(email: Dict[str, Any]) -> str:
    body = email.get("body_text") or email.get("body") or ""
    if isinstance(body, str) and body.strip():
        return body
    html_body = email.get("body_html") or ""
    if not isinstance(html_body, str):
        return ""
    return re.sub(r"<[^>]+>", " ", html_body)


def change_mail_auto(
    spc_st: str,
    mail_email: str,
    mail_password: str,
    proxies: Optional[ProxyDict] = None,
    max_wait_seconds: int = 180,
    poll_interval: float = 5.0,
) -> Dict[str, Any]:
    change_token = change_email_init(spc_st, proxies=proxies)
    if not change_token:
        return {"ok": False, "error": "Bước 1 thất bại: không lấy được change_email_token."}

    d2 = init_email_otp(spc_st, mail_email, proxies=proxies)
    err2 = _api_error(d2)
    if err2:
        return {"ok": False, "error": f"Bước 2 (init_email_otp): {err2}"}

    send_start = time.time()
    seed = send_email_otp(spc_st, mail_email, proxies=proxies)
    if not seed:
        return {"ok": False, "error": "Bước 3 thất bại: không gửi được email OTP."}

    otp_cutoff = send_start - 30.0
    deadline = time.time() + max_wait_seconds

    while time.time() < deadline:
        inbox = get_emails_from_tempmail(mail_email, mail_password)
        if inbox.get("status") == "success":
            emails = list(inbox.get("emails") or [])
            emails.sort(key=lambda e: _email_ts_unix(e) or 0.0, reverse=True)
            for em in emails:
                ts = _email_ts_unix(em)
                if ts is not None and ts < otp_cutoff:
                    continue
                otp = parse_shopee_otp_from_body(_email_body_plain(em) or "")
                if not otp:
                    continue
                email_token = verify_email_otp(spc_st, mail_email, otp, seed, proxies=proxies)
                if not email_token:
                    return {"ok": False, "error": "Xác thực OTP thất bại (mã sai hoặc hết hạn)."}
                commit_res = change_email_commit(
                    spc_st,
                    change_token,
                    mail_email,
                    email_token,
                    proxies=proxies,
                )
                if commit_res.get("ok"):
                    return {
                        "ok": True,
                        "new_email": mail_email,
                        "mail_password": mail_password,
                    }
                return {
                    "ok": False,
                    "error": commit_res.get("error", "Đổi email (commit) thất bại."),
                }
        time.sleep(poll_interval)

    return {
        "ok": False,
        "error": f"Hết thời gian chờ ({max_wait_seconds}s) - chưa thấy OTP Shopee trong inbox.",
    }


def change_mail_prepare_manual_otp(
    spc_st: str,
    email: str,
    proxies: Optional[ProxyDict] = None,
) -> Dict[str, Any]:
    change_token = change_email_init(spc_st, proxies=proxies)
    if not change_token:
        return {
            "ok": False,
            "error": "Bước 1 thất bại: không lấy được change_email_token.",
        }

    d2 = init_email_otp(spc_st, email, proxies=proxies)
    err2 = _api_error(d2)
    if err2:
        return {"ok": False, "error": f"Bước 2 (init_email_otp): {err2}"}

    seed = send_email_otp(spc_st, email, proxies=proxies)
    if not seed:
        return {"ok": False, "error": "Bước 3 thất bại: không gửi được email OTP."}

    return {
        "ok": True,
        "change_token": change_token,
        "seed": seed,
    }


def change_mail_finish_manual_otp(
    spc_st: str,
    email: str,
    change_token: str,
    seed: str,
    otp: str,
    proxies: Optional[ProxyDict] = None,
) -> Dict[str, Any]:
    otp_clean = (otp or "").strip()
    if not re.fullmatch(r"\d{6}", otp_clean):
        return {"ok": False, "error": "OTP phải là đúng 6 chữ số."}

    email_token = verify_email_otp(spc_st, email, otp_clean, seed, proxies=proxies)
    if not email_token:
        return {"ok": False, "error": "Xác thực OTP thất bại (sai mã hoặc hết hạn)."}

    commit_res = change_email_commit(
        spc_st,
        change_token,
        email,
        email_token,
        proxies=proxies,
    )
    if commit_res.get("ok"):
        return {"ok": True, "new_email": email}
    return {
        "ok": False,
        "error": commit_res.get("error", "Đổi email (commit) thất bại."),
    }


def change_mail_v1(spc_st: str, email: str, proxies: Optional[ProxyDict] = None) -> str:
    change_token = change_email_init(spc_st, proxies=proxies)
    if not change_token:
        return "Loi"

    d2 = init_email_otp(spc_st, email, proxies=proxies)
    if _api_error(d2):
        return "Loi"

    seed = send_email_otp(spc_st, email, proxies=proxies)
    if not seed:
        return "Loi"

    otp = input("Nhập OTP: ").strip()
    email_token = verify_email_otp(spc_st, email, otp, seed, proxies=proxies)
    if not email_token:
        return "Loi"

    res = change_email_commit(spc_st, change_token, email, email_token, proxies=proxies)
    return "OK" if res.get("ok") else "Loi"


if __name__ == "__main__":
    print("Dùng change_mail_v1(spc_st, email) hoặc change_mail_auto từ bot.")
