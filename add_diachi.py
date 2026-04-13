import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib import error, request

AUTOFILL_URL = "https://mall.shopee.vn/api/v4/account/address/autofill"
GEOCODE_URL = "https://mall.shopee.vn/api/v4/geo/geocode_v2"
CREATE_URL = "https://mall.shopee.vn/api/v4/account/address/create_user_address"
DEFAULT_TIMEOUT = 60
DEFAULT_LAT = 21.026140213012695
DEFAULT_LNG = 105.84101104736328


@dataclass
class AddAddressInput:
    spc_st: str
    address: str
    phone: str
    note: str = ""
    name: str = ""
    #: Giống requests: {"http": "http://host:port", "https": "http://host:port"}; None = không proxy.
    proxies: Optional[Dict[str, str]] = None


def normalize_spc_st(cookie: str) -> str:
    raw = (cookie or "").strip()
    if not raw:
        return ""
    if "SPC_ST=" in raw:
        return raw
    return f"SPC_ST={raw}"


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 9:
        return f"0{digits}"
    return digits


def _build_opener(proxies: Optional[Dict[str, str]]):
    if proxies:
        return request.build_opener(request.ProxyHandler(proxies))
    return request.build_opener()


def request_json(
    url: str,
    method: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    proxies: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, Any]]:
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(url=url, data=body, headers=headers, method=method)
    opener = _build_opener(proxies)

    try:
        with opener.open(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(content) if content else {}
    except error.HTTPError as exc:
        content = exc.read().decode("utf-8", errors="replace")
        try:
            payload_err = json.loads(content) if content else {}
        except json.JSONDecodeError:
            payload_err = {"message": content or str(exc)}
        return exc.code, payload_err


def add_address_direct(data: AddAddressInput, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    spc_st = normalize_spc_st(data.spc_st)
    if not spc_st:
        raise ValueError("Missing SPC_ST cookie")

    phone = normalize_phone(data.phone)
    if not phone:
        raise ValueError("Invalid phone number")

    if not data.address.strip():
        raise ValueError("Missing address")

    px = data.proxies
    csrf_token = uuid.uuid4().hex
    page_session_id = str(uuid.uuid4())
    current_lat = DEFAULT_LAT
    current_lng = DEFAULT_LNG

    autofill_input = f"{data.address.strip()} {phone}".strip()

    autofill_headers = {
        "Host": "mall.shopee.vn",
        "Cookie": f"csrftoken={csrf_token}; {spc_st}",
        "Content-Type": "application/json",
        "X-Csrftoken": csrf_token,
        "X-Api-Source": "rn",
        "User-Agent": "iOS app iPhone Shopee appver=36476 language=vi app_type=1 platform=native_ios os_ver=26.1.0 Cronet/102.0.5005.61",
        "Referer": "https://mall.shopee.vn/",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "vi-VN,vi,en-US,en",
    }

    autofill_body = {
        "input": autofill_input,
        "user_lng": current_lng,
        "user_lat": current_lat,
        "request_type": "pasting",
        "use_case": "shopee.account",
        "page_session_id": page_session_id,
        "translate_detailed_address": False,
    }

    autofill_status, autofill_data = request_json(
        AUTOFILL_URL,
        "POST",
        autofill_headers,
        autofill_body,
        timeout=timeout,
        proxies=px,
    )

    if autofill_status != 200:
        raise RuntimeError(f"Autofill failed, HTTP {autofill_status}: {autofill_data}")

    if autofill_data.get("error") != 0:
        raise RuntimeError(
            f"Autofill API error: {autofill_data.get('error_msg', 'Unknown error')}"
        )

    parsed = autofill_data.get("data") or {}
    admin_info = parsed.get("admin_info") or {}
    if not admin_info:
        raise RuntimeError("Autofill succeeded but admin_info is empty")

    detailed_address = (parsed.get("detailed_address") or data.address).strip()
    parsed_name = (parsed.get("name") or data.name or "Nguyen Van A").strip()
    parsed_phone = normalize_phone(parsed.get("phone") or phone)

    geocode_headers = {
        "Host": "mall.shopee.vn",
        "Cookie": f"csrftoken={csrf_token}; {spc_st}",
        "Content-Type": "application/json",
        "X-Api-Source": "rn",
        "User-Agent": "iOS app iPhone Shopee appver=36476 language=vi app_type=1 platform=native_ios os_ver=26.1.0 Cronet/102.0.5005.61",
    }

    geocode_body = {
        "use_case": "shopee.account",
        "components": "country:VN",
        "address_list": [
            {
                "address": detailed_address,
                "address_level1": admin_info.get("admin_division_1", ""),
                "address_level2": admin_info.get("admin_division_2", ""),
                "address_level3": admin_info.get("admin_division_3", ""),
            }
        ],
        "user_lat": str(current_lat),
        "user_lng": str(current_lng),
    }

    geocode_status, geocode_data = request_json(
        GEOCODE_URL,
        "POST",
        geocode_headers,
        geocode_body,
        timeout=timeout,
        proxies=px,
    )

    if geocode_status == 200 and geocode_data.get("error") == 0:
        location = (
            (geocode_data.get("result_list") or [{}])[0]
            .get("geometry", {})
            .get("location", {})
        )
        if "lat" in location and "lng" in location:
            current_lat = location["lat"]
            current_lng = location["lng"]

    note = (data.note or "").strip()
    address_for_create = detailed_address
    if note:
        address_for_create = f"{note} {detailed_address}".strip()

    create_headers = {
        "Host": "mall.shopee.vn",
        "Cookie": spc_st,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Android app Shopee appver=28320 app_type=1",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "vi-VN,vi,en-US,en",
    }

    create_body = {
        "address": {
            "country": "VN",
            "name": parsed_name,
            "phone": parsed_phone,
            "address": address_for_create,
            "state": admin_info.get("admin_division_1", ""),
            "city": admin_info.get("admin_division_2", ""),
            "district": admin_info.get("admin_division_3", ""),
            "geoinfo": {
                "geoinfo_confirm": True,
                "user_adjusted": False,
                "user_verified": False,
                "region": {
                    "latitude": current_lat,
                    "longitude": current_lng,
                },
            },
            "label_id": 0,
        },
        "address_flag": {},
    }

    create_status, create_data = request_json(
        CREATE_URL,
        "POST",
        create_headers,
        create_body,
        timeout=timeout,
        proxies=px,
    )

    if create_status != 200:
        raise RuntimeError(f"Create address failed, HTTP {create_status}: {create_data}")

    if create_data.get("error") != 0:
        raise RuntimeError(
            f"Create address API error: {create_data.get('error_msg', 'Unknown error')}"
        )

    return {
        "success": True,
        "addressId": (create_data.get("data") or {}).get("addressid"),
        "parsed": {
            "name": parsed_name,
            "phone": parsed_phone,
            "detailedAddress": detailed_address,
            "state": admin_info.get("admin_division_1", ""),
            "city": admin_info.get("admin_division_2", ""),
            "district": admin_info.get("admin_division_3", ""),
            "latitude": current_lat,
            "longitude": current_lng,
        },
        "raw": create_data,
    }


def prompt_if_missing(value: str, label: str, required: bool = True) -> str:
    out = (value or "").strip()
    while required and not out:
        out = input(label).strip()
    if not required and not out:
        out = input(label).strip()
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add Shopee address directly via Shopee APIs"
    )
    parser.add_argument("--spc-st", default="", help="SPC_ST cookie value or full SPC_ST=...")
    parser.add_argument("--address", default="", help="Address text")
    parser.add_argument("--phone", default="", help="Phone number")
    parser.add_argument("--note", default="", help="Optional note appended to address")
    parser.add_argument("--name", default="", help="Optional receiver name")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Request timeout seconds")
    parser.add_argument(
        "--proxy",
        default="",
        help="HTTP(S) proxy URL (vd. http://user:pass@host:port), dùng cho cả http và https",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # spc_st = prompt_if_missing(args.spc_st, "SPC_ST cookie: ", required=True)
    spc_st = "SPC_ST=THg4Tm9YTzIzMzNVQmE5d2NiK/urS+l8Dh5eX617aKREdiesbNoGS6D5WEi0bzmmK92mexhz3OVjm+lVRutwv6yidUpeq+zjJpXdgOTrm0ZZ58MeLkJePhEpoCxXHclaXv5xvQXGElB3MXlUFc+v44C4izalZKjixk4wfuKGIKG82Rw8BW7xKx3cbuGxwX2TuUJxuBYdfkcnLmxu5yLnhuHEIs3Z7tl+ySLJX6jmFNI=.AOOzj88DFrqRhIMdMM8AAuzcSYBey48cXPRpuoff6ywX"
    # address = prompt_if_missing(args.address, "Address: ", required=True)
    address = "20 Trần đình tri, Hòa Minh, Liên chiểu, Đà Nẵng"
    # phone = prompt_if_missing(args.phone, "Phone: ", required=True)
    phone = "0376585452"

    # note = (args.note or "").strip()
    # if not note:
    #     note = input("Note (optional, Enter to skip): ").strip()

    # name = (args.name or "").strip()
    # if not name:
    #     name = input("Receiver name (optional, Enter to auto): ").strip()
    name = "Nguyễn Văn A"

    proxy_url = (args.proxy or "").strip()
    proxies: Optional[Dict[str, str]] = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    payload = AddAddressInput(
        spc_st=spc_st,
        address=address,
        phone=phone,
        note="",
        name=name,
        proxies=proxies,
    )

    try:
        result = add_address_direct(payload, timeout=args.timeout)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("SUCCESS")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
