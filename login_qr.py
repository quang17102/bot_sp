import base64
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests


DEFAULT_DEVICE_FINGERPRINT = (
    "KV6QS7WFQ4ht2nN6Qh7xYg==|P2PZ2+M8mg8T+Z4b5NLbwzQsm3Bx7RiM/"
    "xMumUuisCwYY0VakW/7LE6YiREuBFGIxjRY957GMpfmBA==|6CLNL99Z6C8Fbv4f|08|3"
)

DEFAULT_X_SAP_RI = "57ffbf69134505ddf11dde3d0901373ae503a0b3b95a2c93820d"
DEFAULT_X_SAP_SEC = (
    "oglV3vz8PLkCe9L5DEfdBKjRItJdXlIq8U+fsP8PhX0rYTT8r//gdYyKJvRerKBo6XuO0OOPf7cd1yZpddRLaLUCaCRm81QMAhN8Z/bXuMYXJEwQECTYjMxjAe30inADPd7Fdl/bKPOLl0iFcXjW0fWuCC0b6qy3rBJg2fbBDRgXD2lizhr/nwYS0qHCfMyOsEViy8tEjMJgjvGlFQGZneyp0XVTjLwEWGvOPRQdykTqIRCbJw3Kg6Nedjb/ARH7G2tby3JyUxbX5mfdrX4kV8oaSt1ixYUm8iEc5fcJgHpKYZGyZNUifpjpA6LDyXR6R5HcT/kHIPJMgiRp6QShw2lQgtwtI4zvnJpy8g8U8cUJW6kmtrI2k0dZCC+NdSaScogF4RYvBm1PVWVEy9I0eYT5r6Kjzg1mXn/ZPYjQswT5m8NZ6fq8uPfV2sn85FcXxoBDf2spnUXh0lUQwPrVQcFOEQN9KG5UabVvvPKwLHNkP0Ue3Ad5HEAV3ZQtFs7WuKx0I9Keo4aPZfKTK684HmonofSaBNfaVU3S7oTsw9Sn8misvs0oC8tQFQU0rp87cMEg+sM8cEP7b0Qd1ymgvW9/3zESLjhdcR/LJMKp4tHcLL+sMJq/OLVO+Nvztd/VUy5n2X/pvkrIsQl4gNWWAVGacPQCfGgDejkKd9Ro6ZEF90LFFYddjEDG4upJGVrgX9d2Ii/jjBav+r+tyVz4I/zN/5aJVQde61QDW/ErJUfyCS3F0cBwGwW1OrGUMTqZpTn8r1nGcV3dmzIi8ICjNNqAoWZzEcpOj6wH/TotwTwYcdaIlfnsqYGPwYbGdHK8pf5SY0ahrM2DKRHMEJzYFyHHQZWnXcs9M+3Lfe3obLCYPLnBfr0qOJ22mrql9SyzWKy/H8DGLGOfJ6neJIkxhdXxVaxH49deavB8ooSrOHUJl23KbjIm1injIICimkCNijNZkyRg3uHorTjEtHNVQTG1kCvH4wZ2EFUa/ukGtyA6xaTglnjbXld9ibop7HUARTzPePLX9WNppH0Gi3yg7bxLPsMfp7EZuz0Kk8eW1hc++Mpbf89IM5+TmOpV4impOV71LudZwalGRX1B7w7N9aM522QS/JMYhSMTXjUcf19E0L3evJGdRn/DbSGT+WEjzSCdbgyU4fIlzbrLT3L0OmS8SPeSZaYD5bqiBRQeOrxz8VchwWveLl4GhH/YAvZUJlDmWkMh9YP8sdLNdp0xTmkP4rTlPH084KxUwmzNH3paTJEa9TiK7fWeNbd1IyXz9m5bcXiHVoPBVbP3p0i1QHUfKAlgB4gZreQApWLFWRC6GrHaM7pXBGtsJvjXsMg7nULfB2aUUYAg1Kj6iMxLk8CZmF4GMWwItV0t/tJrdEWnuAkxGD6efIkNUcpz3CtcKvEX2mIfwk+1aNoOZWA8ExH8bOPInedPkVx3bQF9tEWiA6mO7qFIDjo1K2N7dA2ycS/MSkFITwijxmBH23Jd+/IzPHdB3dBECIok/Pn4sUVSsDLNs3LkewFrerqGBKzKReTJ7LGxa8qBftXiolvihXq0UHCg6VOWPNNszHElQmKHnZQk36PAPzgArAERyjBF1M5hY4kKQqLX9jehusjMid6UDoJKJB7X6ubWvyMuNuP/I+74i9HiEXhrYJcKA1f+yr0xv5+xYRasr+XqSrLud0SjV/d5QzE7wOdnNp8GPdry772VEk7rGsnR/xOgHUp16mhshScGVrMk1VbLfV44Kudt7wbd3M0rFW7cp+irgFTUwOZHo3j5Ioa0+sEGRgu59g1wggLnSKLX11Y1MoY2EGJDMzACysVGEKODF9HW141O5D9gQKI/pTBdYtqhYObyBI/SS86Od1Rwoc9cMHWpHR7BKKb7a+R8IJJop3JDoUuUhQWbjDlr6TB1a43q9mrT2chUoue5EyAh8ZQrOK=="
)

DEFAULT_COOKIE = (
    "_gcl_au=1.1.286162037.1774190334; "
    "csrftoken=ku2UYVwNWJDUzItKYVfkJPfJlhfqnIdx; "
    "_sapid=d32782196bf16571d67a4e1b58f7f16bc2b1c4706ee1bf2bd9f2ff16; "
    "_QPWSDCXHZQA=a4fa2331-c947-4b78-cde4-d33b792ad512; "
    "REC7iLP4Q=a886fc52-3f2e-4538-b76c-3071cce7d819; "
    "SPC_R_T_ID=CdyoeVGW59jYLIfSyZjz8uTjn869pcVyv3loDdRfP4ZZ7yQiXfqjWHqPZW8h9EPnkH8KtKZfot59h5/Tn2VhusEv0pK1t8PRQ/Tb7u37Ns1Ny4GUIFcAnx2+krSF3lsF0RLuRK1KSkAA+TjhuxAuqsUQvCrCKfNGDCWtfiV6L+k=; "
    "SPC_R_T_IV=dzZtRlI0YXVyZG1OR1NQYQ==; "
    "SPC_T_ID=CdyoeVGW59jYLIfSyZjz8uTjn869pcVyv3loDdRfP4ZZ7yQiXfqjWHqPZW8h9EPnkH8KtKZfot59h5/Tn2VhusEv0pK1t8PRQ/Tb7u37Ns1Ny4GUIFcAnx2+krSF3lsF0RLuRK1KSkAA+TjhuxAuqsUQvCrCKfNGDCWtfiV6L+k=; "
    "SPC_T_IV=dzZtRlI0YXVyZG1OR1NQYQ==; "
    "SPC_SI=KMm3aQAAAAA2UWVNYzlyMw+QnQAAAAAAV2QzckdmSVA=; "
    "SPC_SEC_SI=v1-bjg1OWF6NGZvSDdWZEVuQlOctEhtQ3slFHADN7Eb6EUEW8BcdC5B/XjqJzw7bnsnh/BPKW1R22wbDsi+DKMCxNO9nMARSio281f1CqFLkpM=; "
    "SPC_F=4rC0AC3AKTm7ORMIIpOYIx3PI1Tyk8W4; "
    "REC_T_ID=daaefbae-25fc-11f1-a3f4-e2d98aa9a48e; "
    "SPC_CLIENTID=NHJDMEFDM0FLVG03kjowsboverxfgziw; "
    "_fbp=fb.1.1774190335881.14876088798636906; "
    "_ga=GA1.1.1616919213.1774190337; "
    "shopee_webUnique_ccd=KV6QS7WFQ4ht2nN6Qh7xYg%3D%3D%7CP2PZ2%2BM8mg8T%2BZ4b5NLbwzQsm3Bx7RiM%2FxMumUuisCwYY0VakW%2F7LE6YiREuBFGIxjRY957GMpfmBA%3D%3D%7C6CLNL99Z6C8Fbv4f%7C08%7C3; "
    "ds=a401ad6bc712a85ada6239eb17ecf778; "
    "language=vi; "
    "_ga_4GPP1ZXG63=GS2.1.s1774190336$o1$g1$t1774190343$j53$l0$h2037511400"
)


def _extract_cookie_value(cookie_string, key):
    pattern = rf"(?:^|;\s*){re.escape(key)}=([^;]*)"
    match = re.search(pattern, cookie_string or "")
    return match.group(1) if match else ""


def gen_qr_login():
    """Generate Shopee QR code for login."""
    session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        resp = session.get(
            "https://shopee.vn/api/v2/authentication/gen_qrcode",
            headers=headers,
            timeout=(5, 20),
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") or {}
        qrcode_base64 = data.get("qrcode_base64")
        qrcode_id = data.get("qrcode_id")

        if not qrcode_base64 or not qrcode_id:
            return {"status": "error", "message": "Khong nhan duoc ma QR."}

        return {
            "status": "success",
            "qrcode_base64": qrcode_base64,
            "qrcode_id": qrcode_id,
        }
    except requests.Timeout:
        return {"status": "error", "message": "Het thoi gian cho (timeout)."}
    except requests.RequestException as e:
        return {"status": "error", "message": f"Loi mang: {e}"}


def save_qr_png(qrcode_base64, output_path=None):
    """Decode base64 QR image and save to PNG file."""
    if not qrcode_base64:
        return {"status": "error", "message": "Thieu du lieu qrcode_base64"}

    if output_path is None:
        output_path = Path(__file__).with_name("qr.png")
    else:
        output_path = Path(output_path)

    b64_data = qrcode_base64
    if "," in qrcode_base64 and qrcode_base64.startswith("data:image"):
        b64_data = qrcode_base64.split(",", 1)[1]

    try:
        png_bytes = base64.b64decode(b64_data)
        output_path.write_bytes(png_bytes)
        return {"status": "success", "file": str(output_path)}
    except Exception as e:
        return {"status": "error", "message": f"Khong the luu qr.png: {e}"}


def get_qr_status(qrcode_id):
    """Check Shopee QR login status by qrcode_id."""
    session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        resp = session.get(
            f"https://shopee.vn/api/v2/authentication/qrcode_status?qrcode_id={quote(qrcode_id)}",
            headers=headers,
            timeout=(5, 20),
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {"status": "success", "data": data}
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def login_with_qr(
    qrcode_token,
    headers=None,
    cookie_string=None,
    device_fingerprint=None,
):
    """Login QR using request format close to browser curl capture."""
    if not qrcode_token:
        return {"status": "error", "message": "Thieu qrcode_token"}

    cookie_string = cookie_string or os.getenv("SHOPEE_COOKIE", DEFAULT_COOKIE)
    device_fingerprint = device_fingerprint or os.getenv(
        "SHOPEE_DEVICE_FP", DEFAULT_DEVICE_FINGERPRINT
    )
    csrf_token = _extract_cookie_value(cookie_string, "csrftoken") or os.getenv(
        "SHOPEE_CSRFTOKEN", ""
    )

    request_headers = {
        "accept": "application/json",
        "accept-language": "vi,en;q=0.9",
        "af-ac-enc-dat": os.getenv("SHOPEE_AF_AC_ENC_DAT", "f1ec98703e6d2bb7"),
        "af-ac-enc-sz-token": os.getenv(
            "SHOPEE_AF_AC_ENC_SZ_TOKEN", DEFAULT_DEVICE_FINGERPRINT
        ),
        "content-type": "application/json",
        "origin": "https://shopee.vn",
        "priority": "u=1, i",
        "referer": "https://shopee.vn/buyer/login/qr?next=https%3A%2F%2Fshopee.vn%2Fuser%2Fvoucher-wallet",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
        "x-api-source": "pc",
        "x-csrftoken": csrf_token,
        "x-requested-with": "XMLHttpRequest",
        "x-sap-ri": os.getenv("SHOPEE_X_SAP_RI", DEFAULT_X_SAP_RI),
        "x-sap-sec": os.getenv("SHOPEE_X_SAP_SEC", DEFAULT_X_SAP_SEC),
        "x-shopee-language": "vi",
        "x-sz-sdk-version": "1.12.33",
        "cookie": cookie_string,
    }
    if headers:
        request_headers.update(headers)

    if not request_headers.get("x-csrftoken"):
        return {
            "status": "error",
            "message": "Thieu x-csrftoken. Kiem tra csrftoken trong cookie hoac env SHOPEE_CSRFTOKEN.",
        }

    if not request_headers.get("x-sap-ri") or not request_headers.get("x-sap-sec"):
        return {
            "status": "error",
            "message": "Thieu x-sap-ri/x-sap-sec. Can truyen headers hoac set env SHOPEE_X_SAP_RI, SHOPEE_X_SAP_SEC.",
        }

    session = requests.Session()

    login_data = {
        "qrcode_token": qrcode_token,
        "stay_logged_in": False,
        "device_sz_fingerprint": device_fingerprint,
        "client_identifier": {"security_device_fingerprint": device_fingerprint},
    }

    try:
        login_resp = session.post(
            "https://shopee.vn/api/v2/authentication/qrcode_login",
            json=login_data,
            headers=request_headers,
            timeout=(5, 20),
        )

        try:
            login_body = login_resp.json()
        except ValueError:
            login_body = {"raw": login_resp.text}

        login_resp.raise_for_status()

        home_resp = session.get("https://shopee.vn", timeout=(5, 20))

        cookies = {
            c.name: c.value for c in session.cookies if c.name in ["SPC_F", "SPC_ST"]
        }

        if isinstance(login_body, dict) and login_body.get("error") not in (None, 0):
            return {
                "status": "error",
                "message": login_body.get("error_msg") or "Shopee tra ve loi login QR",
                "login_api": login_body,
                "cookies": cookies,
            }

        if not cookies:
            return {
                "status": "error",
                "message": "Dang nhap QR thanh cong nhung khong lay duoc SPC_F/SPC_ST",
                "login_api": login_body,
                "cookies": cookies,
            }

        return {"status": "success", "cookies": cookies, "login_api": login_body}
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def run_qr_login_flow(headers=None, poll_interval=2, max_wait_seconds=180):
    """Auto flow: gen QR -> save qr.png -> poll status -> login when confirmed."""
    gen_result = gen_qr_login()
    if gen_result.get("status") != "success":
        return gen_result

    save_result = save_qr_png(gen_result.get("qrcode_base64"))
    if save_result.get("status") != "success":
        return save_result

    qrcode_id = gen_result.get("qrcode_id")
    started_at = time.time()

    while True:
        status_result = get_qr_status(qrcode_id)
        if status_result.get("status") != "success":
            return status_result

        data = status_result.get("data") or {}
        qr_status = data.get("status", "")
        qrcode_token = data.get("qrcode_token", "")

        if qr_status == "CONFIRMED":
            if not qrcode_token:
                return {
                    "status": "error",
                    "message": "QR da CONFIRMED nhung khong co qrcode_token",
                    "qr_status": qr_status,
                }

            login_result = login_with_qr(qrcode_token, headers=headers)
            login_result["qr_status"] = qr_status
            login_result["qr_file"] = save_result.get("file")
            return login_result

        if max_wait_seconds and (time.time() - started_at) >= max_wait_seconds:
            return {
                "status": "error",
                "message": "Qua thoi gian cho xac nhan QR",
                "qr_status": qr_status,
                "qr_file": save_result.get("file"),
            }

        print(f"[QR STATUS] {qr_status}")
        time.sleep(poll_interval)


if __name__ == "__main__":
    result = run_qr_login_flow()
    print(json.dumps(result, ensure_ascii=False, indent=2))
