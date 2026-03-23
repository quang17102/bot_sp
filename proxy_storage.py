import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests


_FILE_PATH = Path(__file__).with_name("proxy_keys.json")


def _load_all() -> Dict[str, Dict[str, str]]:
    """
    Đọc toàn bộ map proxy keys từ file.
    Cấu trúc:
    {
      "user_id_str": {
        "proxy_type": "KEY_VALUE",
        ...
      },
      ...
    }
    """
    if not _FILE_PATH.exists():
        return {}
    try:
        content = _FILE_PATH.read_text(encoding="utf-8")
        if not content.strip():
            return {}
        data = json.loads(content)
        if isinstance(data, dict):
            # Đảm bảo value là dict[str, str]
            normalized: Dict[str, Dict[str, str]] = {}
            for uid, mapping in data.items():
                if isinstance(mapping, dict):
                    normalized[str(uid)] = {
                        str(k): str(v) for k, v in mapping.items()
                    }
            return normalized
    except Exception:
        # Nếu file hỏng, trả về rỗng để tránh crash bot.
        return {}
    return {}


def _save_all(data: Dict[str, Dict[str, str]]) -> None:
    """
    Ghi toàn bộ map proxy keys ra file.
    """
    text = json.dumps(data, ensure_ascii=False, indent=2)
    _FILE_PATH.write_text(text, encoding="utf-8")


def save_user_proxy_key(user_id: int, proxy_type: str, key: str) -> None:
    """
    Lưu / cập nhật key proxy cho một user và một loại proxy.

    user_id: Telegram user id.
    proxy_type: Tên loại proxy (ví dụ: 'kiot', 'mobile', 'residential_vn_bac', ...).
    key: Giá trị key tương ứng.
    """
    user_id_str = str(user_id)
    proxy_type = proxy_type.strip()
    key = key.strip()
    if not proxy_type or not key:
        return

    data = _load_all()
    user_map = data.get(user_id_str) or {}
    user_map[proxy_type] = key
    data[user_id_str] = user_map
    _save_all(data)


def get_user_proxy_key(user_id: int, proxy_type: str) -> Optional[str]:
    """
    Lấy key proxy của user cho một loại cụ thể.
    """
    user_id_str = str(user_id)
    data = _load_all()
    user_map = data.get(user_id_str) or {}
    return user_map.get(proxy_type.strip())


def list_user_proxy_keys(user_id: int) -> Dict[str, str]:
    """
    Lấy toàn bộ các cặp (proxy_type -> key) của một user.
    """
    user_id_str = str(user_id)
    data = _load_all()
    user_map = data.get(user_id_str) or {}
    # Sao chép để tránh sửa trực tiếp cấu trúc bên trong cache
    return {str(k): str(v) for k, v in user_map.items()}


def delete_user_proxies(user_id: int) -> None:
    """
    Xóa toàn bộ proxy (keys + cache) của một user.

    Được sử dụng bởi command /delpx.
    """
    user_id_str = str(user_id)
    data = _load_all()
    if user_id_str in data:
        del data[user_id_str]
        _save_all(data)


# --------- Helper lấy proxy theo thứ tự ưu tiên ---------
try:
    # Import chậm để tránh vòng lặp import
    from proxy import get_proxy_kiotproxy, get_proxy_proxyxoay
except ImportError:
    # Khi chạy trong môi trường không có module proxy (ví dụ: tool / linter),
    # các hàm phụ thuộc vào proxy sẽ không hoạt động.
    get_proxy_kiotproxy = None  # type: ignore
    get_proxy_proxyxoay = None  # type: ignore


def _is_proxy_live(proxies: Dict[str, str], timeout: int = 5) -> bool:
    """
    Kiểm tra proxy có live hay không bằng cách gọi api.ipify.org.

    Returns:
        True nếu request qua proxy thành công (HTTP 200), ngược lại False.
    """
    try:
        resp = requests.get(
            "https://api.ipify.org/?format=json",
            proxies=proxies,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return False
        # Thử parse JSON để chắc chắn proxy không trả rác
        _ = resp.json()
        return True
    except Exception:
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
    data = _load_all()
    user_id_str = str(user_id)
    user_map = data.get(user_id_str) or {}

    # 1. Ưu tiên KiotProxy
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

    # 2. VNProxy (proxyxoay) với cơ chế cache proxy thực tế
    vn_key = user_map.get("vnpx")           # API key proxyxoay do /vnpx lưu
    vn_cached = user_map.get("vnpx_proxy")  # proxy ip:port đã cache (nếu có)

    # 2a. Thử gọi API proxyxoay để lấy proxy mới
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

            # Bỏ qua check live: luôn cache và trả về nếu API trả proxy hợp lệ
            http_val = formatted.get("http", "")
            if http_val.startswith("http://"):
                http_val = http_val[len("http://") :]
            user_map["vnpx_proxy"] = http_val
            data[user_id_str] = user_map
            _save_all(data)
            return formatted, "vnpx"

    # 2b. Nếu API lỗi hoặc proxy mới không live, thử dùng proxy VN đã cache
    if vn_cached:
        ip_port = str(vn_cached).strip()
        if ip_port:
            cached = {
                "http": f"http://{ip_port}",
                "https": f"http://{ip_port}",
            }
            if _is_proxy_live(cached):
                return cached, "vnpx_cached"
    # 3. Không có proxy phù hợp
    return None, None

