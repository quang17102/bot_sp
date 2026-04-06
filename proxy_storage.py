from typing import Dict, Optional, Tuple

import requests

from tg_supabase.proxy_keys_db import (
    delete_user_proxies,
    get_user_active_proxy_map,
    get_user_proxy_key,
    list_user_proxy_keys,
    save_user_proxy_key,
)

__all__ = [
    "save_user_proxy_key",
    "get_user_proxy_key",
    "list_user_proxy_keys",
    "delete_user_proxies",
    "get_user_best_proxy",
]

# --------- Helper lấy proxy theo thứ tự ưu tiên ---------
try:
    from proxy import get_proxy_kiotproxy, get_proxy_proxyxoay
except ImportError:
    get_proxy_kiotproxy = None  # type: ignore
    get_proxy_proxyxoay = None  # type: ignore


def _is_proxy_live(proxies: Dict[str, str], timeout: int = 5) -> bool:
    try:
        resp = requests.get(
            "https://api.ipify.org/?format=json",
            proxies=proxies,
            timeout=timeout,
        )
        print(f"resp:{resp}")
        if resp.status_code != 200:
            return False
        _ = resp.json()
        return True
    except Exception as e:
        print(f"Exception:{e}")
        return False


def get_user_best_proxy(user_id: int) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Lấy proxy cho user theo thứ tự ưu tiên:
      1. KiotProxy (key lưu dưới type 'kiot', qua /kipx)
      2. VNProxy (key lưu dưới type 'vnpx', qua /vnpx) với cache proxy thực tế

    Returns:
        (proxies, source)
        - proxies: dict {"http": "...", "https": "..."} đã chuẩn hóa scheme hoặc None nếu không có proxy
        - source:
            - "kiot"          -> đang dùng KiotProxy
            - "kiot_expired"  -> key KiotProxy đã hết hạn
            - "vnpx"          -> đang dùng VNProxy (proxyxoay, lấy mới)
            - "vnpx_cached"   -> đang dùng VNProxy cache
            - None            -> không có proxy phù hợp
    """
    user_map = get_user_active_proxy_map(user_id)
    print(f"user_map:{user_map}")
    kiot_key = user_map.get("kiot")
    if kiot_key and get_proxy_kiotproxy is not None:
        result = get_proxy_kiotproxy(kiot_key)
        if result == "KEY_EXPIRED":
            return None, "kiot_expired"
        if isinstance(result, dict) and result:
            formatted: Dict[str, str] = {}
            for k, v in result.items():
                v_str = str(v)
                if v_str.startswith("http://") or v_str.startswith("https://"):
                    formatted[k] = v_str
                else:
                    formatted[k] = f"http://{v_str}"
            return formatted, "kiot"

    vn_key = user_map.get("vnpx")
    vn_cached = user_map.get("vnpx_proxy")

    if vn_key and get_proxy_proxyxoay is not None:
        result = get_proxy_proxyxoay(vn_key)
        if isinstance(result, dict) and result:
            formatted: Dict[str, str] = {}
            for k, v in result.items():
                v_str = str(v)
                if v_str.startswith("http://") or v_str.startswith("https://"):
                    formatted[k] = v_str
                else:
                    formatted[k] = f"http://{v_str}"

            http_val = formatted.get("http", "")
            if http_val.startswith("http://"):
                http_val = http_val[len("http://") :]
            save_user_proxy_key(user_id, "vnpx_proxy", http_val)
            return formatted, "vnpx"
    print(f"vn_cached:{vn_cached}")
    if vn_cached:
        ip_port = str(vn_cached).strip()
        if ip_port:
            cached = {
                "http": f"http://{ip_port}",
                "https": f"http://{ip_port}",
            }
            if _is_proxy_live(cached):
                return cached, "vnpx_cached"
    return None, None
