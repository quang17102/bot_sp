import requests
from typing import Literal, Dict, Any


Region = Literal["bac", "trung", "nam", "random"]


def get_new_proxy_kiotproxy(key: str, region: Region = "random", timeout: int = 5) -> Dict[str, Any]:
    """
    Gọi API KiotProxy để lấy / đổi proxy mới cho một key.

    Args:
        key: Proxy key của bạn (bắt buộc).
        region: Vùng proxy: 'bac' | 'trung' | 'nam' | 'random'. Mặc định: 'random'.
        timeout: Timeout (giây) cho HTTP request.

    Returns:
        Dict chứa toàn bộ JSON response của API.
        - Nếu thành công: theo format tài liệu (data, success, code, status, ...)
        - Nếu lỗi mạng / parse JSON lỗi: trả về {"success": False, "error": "..."}
    """
    base_url = "https://api.kiotproxy.com/api/v1/proxies/new"
    params = {
        "key": key,
        "region": region,
    }

    try:
        resp = requests.get(base_url, params=params, timeout=timeout)
        # Nếu API luôn trả JSON dù code != 200, cứ cố parse JSON trước
        try:
            data = resp.json()
        except ValueError:
            return {
                "success": False,
                "code": resp.status_code,
                "status": "HTTP_ERROR",
                "error": f"Cannot parse JSON, status={resp.status_code}",
                "raw": resp.text,
            }

        # Bổ sung HTTP status vào kết quả cho tiện debug
        if isinstance(data, dict):
            data.setdefault("http_status", resp.status_code)
        return data

    except requests.RequestException as exc:
        return {
            "success": False,
            "status": "REQUEST_EXCEPTION",
            "error": str(exc),
        }

def get_current_proxy_kiotproxy(key: str, region: Region = "random", timeout: int = 5) -> Dict[str, Any]:
    """
    Gọi API KiotProxy để lấy / đổi proxy mới cho một key.

    Args:
        key: Proxy key của bạn (bắt buộc).
        region: Vùng proxy: 'bac' | 'trung' | 'nam' | 'random'. Mặc định: 'random'.
        timeout: Timeout (giây) cho HTTP request.

    Returns:
        Dict chứa toàn bộ JSON response của API.
        - Nếu thành công: theo format tài liệu (data, success, code, status, ...)
        - Nếu lỗi mạng / parse JSON lỗi: trả về {"success": False, "error": "..."}
    """
    base_url = "https://api.kiotproxy.com/api/v1/proxies/current?key=" + key
    try:
        resp = requests.get(base_url, timeout=timeout)
        # Nếu API luôn trả JSON dù code != 200, cứ cố parse JSON trước
        try:
            data = resp.json()
        except ValueError:
            return {
                "success": False,
                "code": resp.status_code,
                "status": "HTTP_ERROR",
                "error": f"Cannot parse JSON, status={resp.status_code}",
                "raw": resp.text,
            }

        # Bổ sung HTTP status vào kết quả cho tiện debug
        if isinstance(data, dict):
            data.setdefault("http_status", resp.status_code)
        return data

    except requests.RequestException as exc:
        return {
            "success": False,
            "status": "REQUEST_EXCEPTION",
            "error": str(exc),
}


import requests

def test_google_with_proxy():
    proxies = {
        "http": "http://171.235.99.98:15652",
        "https": "http://171.235.99.98:15652",  # nhiều proxy HTTP vẫn dùng cho HTTPS
    }

    try:
        resp = requests.get(
            "https://www.ipify.org/",
            proxies=proxies,
            timeout=15,
        )
        print("Status code:", resp.status_code)
        print("URL:", resp.url)
        print("Body (200 ký tự đầu):")
        print(resp.text)
    except requests.RequestException as e:
        print("Lỗi request:", e)

def get_proxy_kiotproxy(key: str, timeout: int = 3) -> Dict[str, Any]:
    result = get_new_proxy_kiotproxy(key, timeout=timeout)
    if result["success"]:
        proxies = {
        "http": result["data"]["http"],
        "https": result["data"]["http"],  # nhiều proxy HTTP vẫn dùng cho HTTPS
    }
        return proxies
    else:
        if result["error"] == "KEY_EXPIRED":
            return "KEY_EXPIRED"
        result = get_current_proxy_kiotproxy(key, timeout=timeout)
        if result["success"]:
            proxies = {
            "http": result["data"]["http"],
            "https": result["data"]["http"],  # nhiều proxy HTTP vẫn dùng cho HTTPS
            }
            return proxies
        else:
            return None

def get_proxy_proxyxoay(key: str) -> dict | None:
    """
    Gọi API proxyxoay.shop để lấy proxy.

    Args:
        key: keyxoay của bạn

    Returns:
        dict proxies dạng {"http": "...", "https": "..."} hoặc None nếu lỗi
    """
    url = "https://proxyxoay.shop/api/get.php"
    params = {
        "key": key,
        "nhamang": "random",
        "tinhthanh": 0,
        "whitelist": "",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        print(f"data:{data}")

        # API trả về dạng JSON, trong đó field "proxyhttp" có giá trị "ip:port::"
        ip_port_raw = data.get("proxyhttp", "") or ""
        # Xoá phần '::' dư ở cuối nếu có
        ip_port = ip_port_raw.split("::", 1)[0].strip()

        if ":" not in ip_port:
            # Không đúng định dạng ip:port → trả về None để debug
            return None
        proxies = {
            "http": f"{ip_port}",
            "https": f"{ip_port}",
        }
        print(f"proxies:{proxies}")
        return proxies
    except requests.RequestException as e:
        print("Lỗi gọi proxyxoay:", e)
        return None

if __name__ == "__main__":
    test_key = "Kaa53e94ecd954a0eb3de2f70a855c5ba"
    result = get_proxy_kiotproxy(test_key)
    print(result)