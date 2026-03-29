import requests
import random
import string
from typing import List, Dict, Any, Optional, Tuple

DOMAINS_URL = "https://cheapluxurymail.xyz/domains"
REGISTER_URL = "https://cheapluxurymail.xyz/register"


def get_domains() -> List[str]:
    """
    Gọi API lấy danh sách domain khả dụng, chọn ngẫu nhiên một domain.

    Returns:
        List một phần tử là domain được chọn, ví dụ: ["example.com"].
        Nếu lỗi hoặc không có domain thì trả về list rỗng.
    """
    try:
        resp = requests.get(DOMAINS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        domains = data.get("data", {}).get("domains", [])
        if isinstance(domains, list):
            cleaned = [str(d).strip() for d in domains if str(d).strip()]
            if not cleaned:
                return []
            return [random.choice(cleaned)]
        return []
    except Exception as e:
        print(f"get_domains error: {e}")
        return []


def get_domains_with_proxy(proxies: Optional[Dict[str, str]] = None) -> List[str]:
    """
    Gọi API lấy danh sách domain khả dụng (có hỗ trợ proxy), chọn ngẫu nhiên một domain.
    """
    try:
        session = requests.Session()
        if proxies:
            session.proxies.update(proxies)
        resp = session.get(DOMAINS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        domains = data.get("data", {}).get("domains", [])
        if isinstance(domains, list):
            cleaned = [str(d).strip() for d in domains if str(d).strip()]
            if not cleaned:
                return []
            return [random.choice(cleaned)]
        return []
    except Exception as e:
        print(f"get_domains_with_proxy error: {e}")
        return []


def register_email_full(
    local_part: str,
    password: str,
    domain: Optional[str] = None,
    proxies: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """
    Đăng ký email hoàn chỉnh:
      1. Nếu không truyền domain -> tự gọi get_domains() và chọn domain ngẫu nhiên.
      2. Ghép thành email: <local_part>@<domain>.
      3. Gọi API /register để đăng ký.

    Args:
        local_part: phần trước dấu @ (ví dụ: 'johndoe')
        password: mật khẩu cho email
        domain: domain muốn dùng; nếu None sẽ auto chọn domain ngẫu nhiên từ API.
        proxies: dict proxy requests (ví dụ {"http": "...", "https": "..."}), optional.

    Returns:
        (email_đầy_đủ_hoặc_None, password_đã_dùng_hoặc_None, response_json_từ_API_hoặc_error_dict)
    """
    local_part = (local_part or "").strip()
    password = (password or "").strip()

    if not local_part:
        # random local_part: 10 ký tự chữ + số
        alphabet = string.ascii_lowercase + string.digits
        local_part = "".join(random.choice(alphabet) for _ in range(10))

    if not password:
        # random password: 12 ký tự, gồm chữ hoa, chữ thường, số
        alphabet = string.ascii_letters + string.digits
        password = "".join(random.choice(alphabet) for _ in range(12))

    # Nếu chưa truyền domain thì tự lấy domain đầu tiên từ API
    if not domain:
        domains = get_domains_with_proxy(proxies) if proxies else get_domains()
        if not domains:
            return None, None, {
                "status": "error",
                "message": "Không lấy được danh sách domain",
            }
        domain = domains[0]

    domain = domain.strip()
    email = f"{local_part}@{domain}"

    try:
        session = requests.Session()
        if proxies:
            session.proxies.update(proxies)
        resp = session.post(
            REGISTER_URL,
            json={"email": email, "password": password},
            timeout=10,
        )
        # Không raise_for_status để luôn trả JSON response về cho caller xử lý
        data = resp.json()
        return email, password, data
    except Exception as e:
        return None, None, {
            "status": "error",
            "message": f"Lỗi khi gọi API register: {e}",
        }


if __name__ == "__main__":
    # Ví dụ sử dụng nhanh khi chạy trực tiếp file này
    # Truyền chuỗi rỗng để random local_part và password
    full_email, full_password, result = register_email_full("", "")
    print("Email:", full_email)
    print("Password:", full_password)