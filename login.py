# -*- coding: utf-8 -*-
"""
Login v\u00E0 authentication functions cho Shopee API
"""

import hashlib
import requests
import secrets
from typing import Dict, Iterable, Optional
import uuid
import json
import os
from datetime import datetime, timezone

def extract_spc_st_from_response(response: requests.Response) -> Optional[str]:
    raw_headers = response.raw.headers
    set_cookie_headers: Iterable[str] = raw_headers.get_all("Set-Cookie") or []

    for cookie_header in set_cookie_headers:
        pair = cookie_header.split(";", 1)[0]
        if not pair.startswith("SPC_ST="):
            continue
        return pair.split("=", 1)[1]

    return None

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

def extract_spc_st(input_line: str, proxies: dict | None = None) -> str:
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
    print(f"proxies:{proxies}")
    session = requests.Session()
    if proxies:
        session.proxies.update(proxies)

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

def extract_spc_st_and_user_info(
    input_line: str,
    proxies: dict | None = None,
    device_id: str | None = None,
    sc_fe_session: str | None = None,
    sc_fe_ver: str | None = None,
) -> tuple[str | None, dict]:
    """
    Kết hợp:
      1. Đăng nhập để lấy SPC_ST
      2. Gọi get_user_info_by_spc_st để lấy thông tin tài khoản

    Trả về:
      - Nếu thành công: (spc_st, {"status": "success", "message": message_html, "message_format": "HTML"})
      - Nếu lỗi: (None, dict giống handle_cks đang dùng để báo lỗi)
    """
    try:
        try:
            spc_st = extract_spc_st(input_line, proxies=proxies)
        except Exception as e:
            print(f"Error: {e}")
            error_msg = str(e)
            # Kiểm tra nếu có F02 trong error message
            if "F02" in error_msg:
                return "\u274c F02: \u0110\u0103ng nh\u1eadp kh\u00f4ng th\u00e0nh c\u00f4ng\n\n"
            else:
                return "\u274c: Lấy cookie thất bại vui lòng thử lại"
        user_info_api = get_user_info_by_spc_st(
            spc_st=spc_st,
            device_id=device_id,
            sc_fe_session=sc_fe_session,
            sc_fe_ver=sc_fe_ver,
            proxies=proxies,
        )
        # Chuẩn hóa dữ liệu giống workers.handle_cks
        user_info = {
            "spc_st": spc_st,
            "username": user_info_api.get("seller_user_info", {})
            .get("data", {})
            .get("user_name", ""),
            "email": user_info_api.get("data", {})
            .get("data", {})
            .get("email", ""),
            "phone": user_info_api.get("data", {})
            .get("data", {})
            .get("phone", ""),
            "created": user_info_api.get("created_at_iso_utc", ""),
        }

        return user_info
    except Exception as e:
        # Lỗi chung: trả về message giống workers.py (207–211)
        return {}


def build_user_info_dict_from_spc_st(
    spc_st: str,
    proxies: dict | None = None,
    device_id: str | None = None,
    sc_fe_session: str | None = None,
    sc_fe_ver: str | None = None,
) -> dict:
    """
    Chuẩn hóa user_info khi đã có SPC_ST (vd. đăng nhập QR), cùng keys với
    dict trả về từ extract_spc_st_and_user_info khi thành công.
    """
    if not (spc_st or "").strip():
        return {}
    user_info_api = get_user_info_by_spc_st(
        spc_st=spc_st,
        device_id=device_id,
        sc_fe_session=sc_fe_session,
        sc_fe_ver=sc_fe_ver,
        proxies=proxies,
    )
    if user_info_api.get("status") == "error":
        return {}
    user_info = {
        "spc_st": spc_st,
        "username": user_info_api.get("seller_user_info", {})
        .get("data", {})
        .get("user_name", ""),
        "email": user_info_api.get("data", {})
        .get("data", {})
        .get("email", ""),
        "phone": user_info_api.get("data", {})
        .get("data", {})
        .get("phone", ""),
        "created": user_info_api.get("created_at_iso_utc", ""),
    }
    return user_info


def build_spc_st_cookie(spc_st: str) -> str:
    raw = (spc_st or "").strip()
    if not raw:
        return ""
    if ";" in raw and "=" in raw:
        return raw
    return raw if raw.startswith("SPC_ST=") else f"SPC_ST={raw}"


def _extract_cookie_value(cookie_value: str, key: str) -> str:
    raw = (cookie_value or "").strip()
    if not raw or not key:
        return ""
    for part in raw.split(";"):
        item = part.strip()
        if item.startswith(f"{key}="):
            return item[len(key) + 1 :]
    return ""


def _cookie_to_dict(cookie_value: str) -> dict:
    data = {}
    raw = (cookie_value or "").strip()
    if not raw:
        return data

    for part in raw.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        key = k.strip()
        if key:
            data[key] = v.strip()
    return data


def _dict_to_cookie(cookie_map: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookie_map.items())


def _merge_cookie(base_cookie: str, session_cookie_map: dict) -> str:
    merged = _cookie_to_dict(base_cookie)
    if isinstance(session_cookie_map, dict):
        for k, v in session_cookie_map.items():
            key = str(k).strip()
            if not key:
                continue
            merged[key] = str(v)
    return _dict_to_cookie(merged)


def _safe_json_response(response: requests.Response) -> tuple[dict | None, str | None]:
    try:
        return response.json(), None
    except ValueError:
        return None, response.text


def _find_created_time(value, path: str = "root") -> tuple[object | None, str]:
    candidate_keys = (
        "create_time",
        "created_at",
        "ctime",
        "createdTime",
        "createdAt",
        "register_time",
        "registerTime",
        "join_time",
        "joined_time",
    )

    if isinstance(value, dict):
        for key in candidate_keys:
            if key in value and value[key] not in (None, ""):
                return value[key], f"{path}.{key}"
        for key, sub_value in value.items():
            found_value, found_path = _find_created_time(sub_value, f"{path}.{key}")
            if found_value is not None:
                return found_value, found_path
        return None, ""

    if isinstance(value, list):
        for index, item in enumerate(value):
            found_value, found_path = _find_created_time(item, f"{path}[{index}]")
            if found_value is not None:
                return found_value, found_path
        return None, ""

    return None, ""


def _to_iso_utc(value) -> str:
    if value is None:
        return ""

    parsed = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
            parsed = int(stripped)
        else:
            return stripped

    if isinstance(parsed, (int, float)):
        timestamp = float(parsed)
        if timestamp > 1_000_000_000_000:
            timestamp = timestamp / 1000.0
        if timestamp > 0:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    return str(value)


def _build_chat_headers(cookie: str, device_id: str) -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "vi,en;q=0.9",
        "cookie": cookie,
        "device-id": device_id,
        "origin": "https://banhang.shopee.vn",
        "referer": "https://banhang.shopee.vn/",
        "shopee-region": "vn",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    }


def _build_seller_headers(cookie: str, sc_fe_session: str, sc_fe_ver: str) -> dict:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "vi,en;q=0.9",
        "cookie": cookie,
        "priority": "u=1, i",
        "referer": "https://banhang.shopee.vn/portal/vn-onboarding/form/291000/291100",
        "sec-ch-ua": "\"Not:A-Brand\";v=\"99\", \"Google Chrome\";v=\"145\", \"Chromium\";v=\"145\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    }
    if sc_fe_session:
        headers["sc-fe-session"] = sc_fe_session
    if sc_fe_ver:
        headers["sc-fe-ver"] = sc_fe_ver
    return headers

def get_user_info_by_spc_st(
    spc_st: str,
    device_id: str | None = None,
    sc_fe_session: str | None = None,
    sc_fe_ver: str | None = None,
    proxies: dict | None = None,
) -> dict:
    if not spc_st:
        return {"status": "error", "message": "Thieu SPC_ST"}

    cookie = build_spc_st_cookie(spc_st)
    if not cookie:
        return {"status": "error", "message": "Cookie khong hop le"}

    if not device_id:
        device_id = str(uuid.uuid4())
    if sc_fe_session is None:
        sc_fe_session = (os.getenv("SHOPEE_SC_FE_SESSION") or "").strip()
    if sc_fe_ver is None:
        sc_fe_ver = (os.getenv("SHOPEE_SC_FE_VER") or "").strip()

    session = requests.Session()
    if proxies:
        session.proxies.update(proxies)
    working_cookie = cookie

    # Bootstrap session from SPC_ST to receive extra cookies (SPC_CDS, SPC_SC_SESSION, ...)
    try:
        bootstrap_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "cookie": working_cookie,
            "referer": "https://banhang.shopee.vn/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        }
        session.get("https://banhang.shopee.vn", headers=bootstrap_headers, timeout=20)
        jar_cookie = session.cookies.get_dict()
        if jar_cookie:
            working_cookie = _merge_cookie(working_cookie, jar_cookie)
    except requests.RequestException:
        # Keep fallback cookie as SPC_ST only if bootstrap fails
        pass

    chat_url = "https://chatbot.seller.shopee.vn/chat/v2/get_user_info"
    chat_headers = _build_chat_headers(cookie=working_cookie, device_id=device_id)

    try:
        response = session.get(chat_url, headers=chat_headers, timeout=20)
        chat_data, chat_raw = _safe_json_response(response)
        if chat_data is None:
            return {
                "status": "error",
                "message": "Khong parse duoc JSON",
                "http_status": response.status_code,
                "raw": chat_raw,
            }

        result = {
            "status": "success" if response.status_code == 200 else "error",
            "http_status": response.status_code,
            "data": chat_data,
        }

        spc_cds = _extract_cookie_value(working_cookie, "SPC_CDS")
        spc_cds_source = "cookie"
        if not spc_cds:
            spc_cds = (os.getenv("SHOPEE_SPC_CDS") or "").strip()
            spc_cds_source = "env.SHOPEE_SPC_CDS"
        if not spc_cds:
            # Fallback: many Shopee endpoints accept a runtime UUID for SPC_CDS
            spc_cds = str(uuid.uuid4())
            spc_cds_source = "generated_uuid"

        seller_url = "https://banhang.shopee.vn/api/selleraccount/user_info/"
        seller_headers = _build_seller_headers(
            cookie=working_cookie,
            sc_fe_session=sc_fe_session or "",
            sc_fe_ver=sc_fe_ver or "",
        )
        seller_params = {"SPC_CDS": spc_cds, "SPC_CDS_VER": 2}
        seller_response = session.get(seller_url, params=seller_params, headers=seller_headers, timeout=20)
        seller_json, seller_raw = _safe_json_response(seller_response)

        result["seller_http_status"] = seller_response.status_code
        result["seller_spc_cds_source"] = spc_cds_source
        if seller_json is None:
            result["seller_user_info"] = {
                "status": "error",
                "message": "Khong parse duoc JSON tu selleraccount/user_info",
                "raw": seller_raw,
            }
            return result

        result["seller_user_info"] = seller_json

        created_value, created_path = _find_created_time(seller_json)
        if created_value is not None:
            result["created_at"] = created_value
            result["created_at_path"] = created_path
            iso_utc = _to_iso_utc(created_value)
            if iso_utc:
                result["created_at_iso_utc"] = iso_utc
        else:
            result["created_at"] = None

        return result
    except requests.RequestException as exc:
        return {"status": "error", "message": f"Loi ket noi: {exc}"}
