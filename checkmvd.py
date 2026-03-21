from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, ProxyHandler, build_opener, urlopen


TRACKING_STATUS_MAP: dict[str, str] = {
    "label_preparing_order": "Dang chuan bi don hang",
    "preparing_order": "Dang chuan bi don hang",
    "label_order_prepared": "Don hang da san sang",
    "order_prepared": "Don hang da san sang",
    "label_to_ship": "Cho gui hang",
    "to_ship": "Cho gui hang",
    "label_to_receive": "Dang giao",
    "to_receive": "Dang giao",
    "order_list_text_to_ship_edt": "Cho gui hang",
    "order_status_text_to_ship_order_edt_cod": "Cho gui hang (COD)",
    "order_status_text_to_ship_order_edt": "Cho gui hang",
    "label_waiting_pickup": "Cho lay hang",
    "waiting_pickup": "Cho lay hang",
    "label_pickup_scheduled": "Da len lich lay hang",
    "pickup_scheduled": "Da len lich lay hang",
    "label_in_transit": "Dang van chuyen",
    "in_transit": "Dang van chuyen",
    "label_on_the_way": "Dang tren duong giao",
    "on_the_way": "Dang tren duong giao",
    "label_out_for_delivery": "Dang giao hang",
    "out_for_delivery": "Dang giao hang",
    "label_delivered": "Da giao hang",
    "delivered": "Da giao hang",
    "label_delivery_confirmed": "Da xac nhan giao hang",
    "delivery_confirmed": "Da xac nhan giao hang",
    "label_completed": "Hoan thanh",
    "completed": "Hoan thanh",
    "label_order_completed": "Don hang hoan thanh",
    "order_completed": "Don hang hoan thanh",
    "label_cancelled": "Da huy",
    "cancelled": "Da huy",
    "label_order_cancelled": "Da huy",
    "order_cancelled": "Da huy",
    "label_cancel_order_reason_admin_901": "Huy boi he thong",
    "cancel_order_reason_admin_901": "Huy boi he thong",
    "label_return_requested": "Yeu cau hoan tra",
    "return_requested": "Yeu cau hoan tra",
    "label_returned": "Da hoan tra",
    "returned": "Da hoan tra",
    "label_refunded": "Da hoan tien",
    "refunded": "Da hoan tien",
    "label_pending_payment": "Cho thanh toan",
    "pending_payment": "Cho thanh toan",
    "label_payment_failed": "Thanh toan that bai",
    "payment_failed": "Thanh toan that bai",
    "label_processing": "Dang xu ly",
    "processing": "Dang xu ly",
    "label_ship_by_date_not_calculated": "Dang xu ly",
    "ship_by_date_not_calculated": "Dang xu ly",
    "label_confirmed": "Da xac nhan",
    "confirmed": "Da xac nhan",
    "label_delivery_failed": "Giao hang that bai",
    "delivery_failed": "Giao hang that bai",
    "label_delivery_attempted": "Da thu giao hang",
    "delivery_attempted": "Da thu giao hang",
    "label_delivery_delayed": "Giao hang bi tre",
    "delivery_delayed": "Giao hang bi tre",
    "label_arrived_at_warehouse": "Da den kho",
    "arrived_at_warehouse": "Da den kho",
    "label_left_warehouse": "Da roi kho",
    "left_warehouse": "Da roi kho",
    "label_at_sorting_center": "Dang tai trung tam phan loai",
    "at_sorting_center": "Dang tai trung tam phan loai",
}

DELIVERING_KEYWORDS = (
    "dang giao",
    "dang van chuyen",
    "dang tren duong giao",
    "dang giao hang",
    "da den kho",
    "da roi kho",
    "trung tam phan loai",
    "cho lay hang",
    "da len lich lay hang",
)

WAITING_CONFIRMATION_KEYWORDS = (
    "dang chuan bi don hang",
    "don hang da san sang",
    "cho gui hang",
    "dang xu ly",
    "da xac nhan",
)

CANCELLED_KEYWORDS = (
    "huy",
    "hoan tra",
    "hoan tien",
)


@dataclass(slots=True)
class CachedOrder:
    order_id: str
    final_total: int | float | str | None
    detail: dict[str, Any]


class ShopeeApiError(RuntimeError):
    pass


def normalize_status_text(value: str | None, fallback: str = "Khong xac dinh") -> str:
    if not value:
        return fallback

    normalized = str(value).strip()
    if not normalized:
        return fallback

    if normalized in TRACKING_STATUS_MAP:
        return TRACKING_STATUS_MAP[normalized]

    lowered = normalized.lower()
    if lowered in TRACKING_STATUS_MAP:
        return TRACKING_STATUS_MAP[lowered]

    if lowered.startswith("label_"):
        without_prefix = lowered.removeprefix("label_")
        if without_prefix in TRACKING_STATUS_MAP:
            return TRACKING_STATUS_MAP[without_prefix]

    return normalized


def ensure_cookie_string(raw_cookie: str) -> str:
    cookie = raw_cookie.strip()
    if not cookie:
        raise ValueError("Cookie SPC_ST khong duoc de trong")

    if cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()

    if "=" in cookie:
        return cookie

    return f"SPC_ST={cookie}"


def format_money(value: Any) -> str:
    if value in (None, ""):
        return "0"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{amount:,.0f}".replace(",", ".")

def format_money_for_total(value: Any) -> str:
    if value in (None, ""):
        return "0"
    try:
        amount = Decimal(str(value))/100000
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{amount:,.0f}".replace(",", ".")


def request_json(
    url: str,
    headers: dict[str, str],
    timeout: int,
    proxies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Gọi GET JSON. Nếu `proxies` có (vd. từ get_user_best_proxy), dùng ProxyHandler."""
    request = Request(url, headers=headers, method="GET")
    try:
        if proxies:
            opener = build_opener(ProxyHandler(proxies))
            response = opener.open(request, timeout=timeout)
        else:
            response = urlopen(request, timeout=timeout)
        try:
            payload = response.read().decode("utf-8", errors="replace")
        finally:
            response.close()
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise ShopeeApiError("Cookie het han hoac bi tu choi") from exc
        raise ShopeeApiError(f"HTTP {exc.code}: {payload[:300]}") from exc
    except URLError as exc:
        raise ShopeeApiError(f"Khong the ket noi Shopee: {exc}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ShopeeApiError(f"Shopee tra ve du lieu khong hop le: {payload[:300]}") from exc

    error_code = data.get("error")
    if error_code not in (None, 0):
        error_message = data.get("error_msg") or f"Shopee error {error_code}"
        raise ShopeeApiError(error_message)

    return data


def build_list_headers(cookie: str) -> dict[str, str]:
    return {
        "User-Agent": "Android app Shopee appver=28320 app_type=1",
        "Cookie": cookie,
        "Content-Type": "application/json",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Request-ID": f"req_{int(time.time() * 1000)}",
    }


def build_logistics_headers(cookie: str) -> dict[str, str]:
    return {
        "Host": "mall.shopee.vn",
        "Cookie": cookie,
        "User-Agent": "iOS app iPhone Shopee appver=36649 language=vi app_type=1 platform=native_ios os_ver=26.2.1 Cronet/102.0.5005.61",
        "X-Shopee-Client-Timezone": "Asia/Ho_Chi_Minh",
        "Accept": "*/*",
        "Referer": "https://mall.shopee.vn/",
    }


def fetch_order_page(
    cookie: str,
    limit: int,
    offset: int,
    timeout: int,
    proxies: dict[str, str] | None = None,
) -> list[CachedOrder]:
    query = urlencode({"limit": limit, "offset": offset})
    url = f"https://shopee.vn/api/v4/order/get_all_order_and_checkout_list?{query}"
    data = request_json(url, build_list_headers(cookie), timeout=timeout, proxies=proxies)
    
    old_orders = data.get("data", {}).get("order_data", {}).get("details_list", []) or []
    new_orders = data.get("new_data", {}).get("order_or_checkout_data", []) or []
    merged: dict[str, CachedOrder] = {}

    for order in old_orders:
        info = (order or {}).get("info_card", {})
        order_id = info.get("order_id")
        if order_id:
            merged[str(order_id)] = CachedOrder(str(order_id), info.get("final_total"), order)

    for item in new_orders:
        detail = (item or {}).get("order_list_detail") or item or {}
        info = detail.get("info_card", {})
        order_id = info.get("order_id")
        if order_id:
            merged[str(order_id)] = CachedOrder(str(order_id), info.get("final_total"), detail)
    return list(merged.values())


def fetch_all_orders(
    cookie: str,
    page_size: int,
    timeout: int,
    max_orders: int | None,
    proxies: dict[str, str] | None = None,
) -> dict[str, CachedOrder]:
    all_orders: dict[str, CachedOrder] = {}
    offset = 0

    while True:
        page_orders = fetch_order_page(
            cookie, limit=page_size, offset=offset, timeout=timeout, proxies=proxies
        )
        if not page_orders:
            break

        new_count = 0
        for order in page_orders:
            if order.order_id not in all_orders:
                all_orders[order.order_id] = order
                new_count += 1
                if max_orders and len(all_orders) >= max_orders:
                    return all_orders

        if new_count == 0:
            break

        offset += page_size
    return all_orders


def fetch_order_detail(
    cookie: str,
    order_id: str,
    timeout: int,
    proxies: dict[str, str] | None = None,
) -> dict[str, Any]:
    query = urlencode({"_oft": 0, "order_id": order_id})
    url = f"https://shopee.vn/api/v4/order/get_order_detail?{query}"
    data = request_json(url, build_list_headers(cookie), timeout=timeout, proxies=proxies)
    return data.get("data", {}) or {}


def fetch_logistics_info(
    cookie: str,
    order_id: str,
    timeout: int,
    proxies: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    query = urlencode({"_oft": 0, "order_id": order_id})
    url = f"https://mall.shopee.vn/api/v4/order/buyer/get_logistics_info?{query}"
    try:
        data = request_json(url, build_logistics_headers(cookie), timeout=timeout, proxies=proxies)
    except ShopeeApiError:
        return None
    return data.get("data") or None


def extract_order_time(detail_data: dict[str, Any]) -> str:
    info_rows = detail_data.get("processing_info", {}).get("info_rows", []) or []
    for row in info_rows:
        if (row or {}).get("info_label", {}).get("text") == "label_odp_order_time":
            return row.get("info_value", {}).get("value") or "Khong co"
    return "Khong co"


def _shipping_extra_from_block(shipping_block: dict[str, Any] | None) -> dict[str, Any]:
    """
    Lấy thêm từ khối shipping: tracking_number, text masked_carrier (hiển thị đơn vị VC...).
    `masked_carrier` có thể là dict (có tracking_number / text) hoặc chuỗi.
    """
    if not isinstance(shipping_block, dict):
        return {}
    out: dict[str, Any] = {}
    mc = shipping_block.get("masked_carrier")
    if isinstance(mc, dict):
        tn = mc.get("tracking_number")
        if tn:
            out["tracking_number"] = str(tn).strip()
        txt = mc.get("text")
        if txt:
            out["masked_carrier_text"] = str(txt).strip()
    elif isinstance(mc, str) and mc.strip():
        out["masked_carrier_text"] = mc.strip()
    if not out.get("tracking_number"):
        tn = shipping_block.get("tracking_number")
        if tn:
            out["tracking_number"] = str(tn).strip()
    return out


def extract_first_item(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Trả về (item đầu tiên trong đơn, dict bổ sung từ shipping / masked_carrier / parcel đầu).
    Dict thứ hai dùng để suy ra mã vận đơn khi shipping top-level chưa có.
    """
    shipping_extra = _shipping_extra_from_block(source.get("shipping"))

    parcel_cards = source.get("info_card", {}).get("parcel_cards", []) or []
    if not parcel_cards:
        order_list_cards = source.get("info_card", {}).get("order_list_cards", []) or []
        if order_list_cards:
            parcel_cards = order_list_cards[0].get("parcel_cards", []) or []

    if parcel_cards:
        pc0 = parcel_cards[0] or {}
        for k, v in _shipping_extra_from_block(pc0.get("shipping")).items():
            if not v:
                continue
            if k == "tracking_number" or not shipping_extra.get(k):
                shipping_extra[k] = v
        item_groups = pc0.get("product_info", {}).get("item_groups", []) or []
        if item_groups:
            items = item_groups[0].get("items", []) or []
            if items:
                return (items[0] or {}, shipping_extra)

    item_groups = source.get("info_card", {}).get("product_info", {}).get("item_groups", []) or []
    if item_groups:
        items = item_groups[0].get("items", []) or []
        if items:
            return (items[0] or {}, shipping_extra)

    return ({}, shipping_extra)


def format_unix_seconds(unix_seconds: int | None) -> str:
    if not unix_seconds:
        return ""
    try:
        dt = datetime.fromtimestamp(int(unix_seconds))
    except (TypeError, ValueError, OSError):
        return ""
    return dt.strftime("%d/%m/%Y %H:%M")


def extract_logistics_summary(logistics_data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not logistics_data:
        return None

    tracking_list = logistics_data.get("tracking_info_list", []) or []
    history: list[dict[str, Any]] = []
    for item in tracking_list:
        history.append(
            {
                "time": format_unix_seconds(item.get("ctime")),
                "description": normalize_status_text(item.get("description"), ""),
                "driver_name": item.get("driver_name") or "",
                "driver_phone": item.get("driver_phone") or "",
                "license_plate": item.get("license_plate_number") or "",
            }
        )

    time_display = logistics_data.get("time_display", {}) or {}
    return {
        "shipping_status": normalize_status_text(logistics_data.get("shipping_status"), ""),
        "carrier_name": logistics_data.get("carrier_name") or logistics_data.get("channel_name") or "Khong xac dinh",
        "tracking_number": logistics_data.get("tracking_number") or "Khong co ma van don",
        "expected_time_type": normalize_status_text(time_display.get("type"), "Ngay nhan hang du kien"),
        "expected_time_text": format_unix_seconds(time_display.get("time")),
        "history": history,
    }


def build_order_record(order_id: str, cached_order: CachedOrder, detail_data: dict[str, Any], logistics_data: dict[str, Any] | None) -> dict[str, Any]:
    source = detail_data or cached_order.detail
    shipping = source.get("shipping", {}) or {}
    tracking_info = shipping.get("tracking_info", {}) or {}
    delivery_info = shipping.get("delivery_info", {}) or {}
    address = source.get("address", {}) or {}
    first_item, shipping_extra = extract_first_item(source)
    logistics = extract_logistics_summary(logistics_data)

    status = normalize_status_text(
        tracking_info.get("description")
        or source.get("status", {}).get("status_label", {}).get("text")
        or source.get("status", {}).get("list_view_status_label", {}).get("text"),
        "Khong xac dinh",
    )

    driver_name = (
        shipping.get("driver_name")
        or tracking_info.get("driver_name")
        or delivery_info.get("driver_name")
        or (logistics or {}).get("history", [{}])[0].get("driver_name")
        or ""
    )
    driver_phone = (
        shipping.get("driver_phone")
        or tracking_info.get("driver_phone")
        or delivery_info.get("driver_phone")
        or (logistics or {}).get("history", [{}])[0].get("driver_phone")
        or ""
    )
    tracking_number = (
        shipping.get("tracking_number")
        or shipping_extra.get("masked_carrier_text")
        or (logistics or {}).get("tracking_number")
    ) or "Khong co ma van don"
    return {
        "order_id": order_id,
        "status": status,
        "tracking_number": tracking_number,
        "order_time": extract_order_time(detail_data) if detail_data else "Khong co",
        "final_total": cached_order.final_total or first_item.get("order_price") or 0,
        "shipping_name": address.get("shipping_name") or "",
        "shipping_phone": address.get("shipping_phone") or "",
        "shipping_address": address.get("shipping_address") or "",
        "item_id": first_item.get("item_id"),
        "model_id": first_item.get("model_id"),
        "shop_id": first_item.get("shop_id"),
        "name": first_item.get("name") or "",
        "model_name": first_item.get("model_name") or first_item.get("model", {}).get("name") or first_item.get("model", {}).get("model_name") or "",
        "image": first_item.get("image") or "",
        "item_price": first_item.get("item_price") or 0,
        "order_price": first_item.get("order_price") or 0,
        "driver_name": driver_name,
        "driver_phone": driver_phone,
        "logistics": logistics,
    }


def classify_status(status: str) -> str:
    lowered = status.lower()
    if any(keyword in lowered for keyword in CANCELLED_KEYWORDS):
        return "cancelled"
    if any(keyword in lowered for keyword in DELIVERING_KEYWORDS):
        return "delivering"
    if any(keyword in lowered for keyword in WAITING_CONFIRMATION_KEYWORDS):
        return "waiting_confirmation"
    return "other"


def print_report(orders: list[dict[str, Any]],) -> None:
    # print("=== Tong quan ===")
    # print(f"Tong so don hang: {stats['total_orders']}")
    # print(f"So don huy: {stats['cancelled_orders']}")
    # print(f"So don dang giao: {stats['delivering_orders']}")
    # print(f"So don dang cho xac nhan: {stats['waiting_confirmation_orders']}")
    # print()

    # print("=== Thong ke theo trang thai ===")
    # for status, count in stats["status_breakdown"].items():
    #     print(f"- {status}: {count}")
    # print()

    print("=== Chi tiet tung don ===")
    for index, order in enumerate(orders, start=1):
        print(f"[{index}] Don hang {order['order_id']}")
        print(f"  Trang thai: {order['status']}")
        print(f"  Ma van don: {order['tracking_number']}")
        print(f"  Thoi gian dat: {order['order_time']}")
        print(f"  Tong tien: {format_money_for_total(order['final_total'])}")
        print(f"  San pham: {order['name'] or 'Khong co ten'}")
        if order.get("model_name"):
            print(f"  Phan loai: {order['model_name']}")
        print(f"  Nguoi nhan: {order['shipping_name'] or 'Khong co'} | {order['shipping_phone'] or 'Khong co'}")
        print(f"  Dia chi: {order['shipping_address'] or 'Khong co'}")
        if order.get("driver_name") or order.get("driver_phone"):
            print(f"  Shipper: {order.get('driver_name') or 'Khong co'} | {order.get('driver_phone') or 'Khong co'}")

        logistics = order.get("logistics")
        if logistics:
            print(f"  Don vi van chuyen: {logistics.get('carrier_name') or 'Khong ro'}")
            if logistics.get("expected_time_text"):
                print(f"  {logistics.get('expected_time_type')}: {logistics.get('expected_time_text')}")
            history = logistics.get("history", []) or []
            for event in history[:5]:
                time_text = event.get("time") or ""
                description = event.get("description") or ""
                print(f"    - {time_text} {description}".rstrip())
        print()


def build_stats(orders: list[dict[str, Any]]) -> dict[str, Any]:
    status_breakdown = Counter(order["status"] for order in orders)
    buckets = Counter(classify_status(order["status"]) for order in orders)
    return {
        "total_orders": len(orders),
        "cancelled_orders": buckets["cancelled"],
        "delivering_orders": buckets["delivering"],
        "waiting_confirmation_orders": buckets["waiting_confirmation"],
        "other_orders": buckets["other"],
        "status_breakdown": dict(status_breakdown.most_common()),
    }


def collect_orders(
    cookie: str,
    page_size: int,
    timeout: int,
    max_orders: int | None,
    include_logistics: bool,
    proxies: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Lấy đơn buyer. `proxies` cùng format requests (http/https) — nên trùng proxy đã dùng khi lấy SPC_ST."""
    cached_orders = fetch_all_orders(
        cookie, page_size=page_size, timeout=timeout, max_orders=max_orders, proxies=proxies
    )
    order_ids = list(cached_orders.keys())

    if not order_ids:
        return []

    orders: list[dict[str, Any]] = []
    for index, order_id in enumerate(order_ids, start=1):
        detail_data: dict[str, Any] = {}
        logistics_data: dict[str, Any] | None = None

        try:
            detail_data = fetch_order_detail(cookie, order_id, timeout=timeout, proxies=proxies)
        except ShopeeApiError:
            detail_data = {}

        if include_logistics:
            logistics_data = fetch_logistics_info(cookie, order_id, timeout=timeout, proxies=proxies)

        orders.append(build_order_record(order_id, cached_orders[order_id], detail_data, logistics_data))
        print(f"Da xu ly {index}/{len(order_ids)} don", file=sys.stderr)
    return orders


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lay danh sach don Shopee tu cookie SPC_ST va thong ke trang thai don hang."
    )
    parser.add_argument("spc_st", nargs="?", help="Gia tri SPC_ST hoac full cookie header")
    parser.add_argument("--page-size", type=int, default=50, help="So don moi lan goi API list, mac dinh 50")
    parser.add_argument("--timeout", type=int, default=15, help="Timeout moi request, mac dinh 15 giay")
    parser.add_argument("--max-orders", type=int, default=None, help="Gioi han so don can lay")
    parser.add_argument("--include-logistics", action="store_true", help="Lay them lich su van chuyen cho tung don")
    parser.add_argument("--output-json", help="Luu ket qua day du ra file JSON")
    return parser.parse_args()

def get_don_hang(cookiess) -> list[dict[str, Any]]:
    args = parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        cookie = ensure_cookie_string(cookiess)
        orders = collect_orders(
            cookie=cookie,
            page_size=args.page_size,
            timeout=args.timeout,
            max_orders=args.max_orders,
            include_logistics=args.include_logistics,
        )
        stats = build_stats(orders)
        report_payload = {
            "summary": stats,
            "orders": orders,
        }

        # if args.output_json:
        #     with open(args.output_json, "w", encoding="utf-8") as file_obj:
        #         json.dump(report_payload, file_obj, ensure_ascii=False, indent=2)
        return orders
        
    except (ShopeeApiError, ValueError) as exc:
        print(f"Loi: {exc}", file=sys.stderr)
        return 1
    return 0

def main() -> int:
    
    # Nếu có truyền SPC_ST/full cookie qua CLI thì dùng,
    # nếu không thì fallback sang coo
    # kie hardcode (dùng để test nhanh).
    cooki = "SPC_ST=YnBteXZrMTRBQ1BBS1hwTItszNp3f3bTfi5O7hjQqcLVe8YKDx17qiRwQ80XChOAenhnlOJayfWuMLkBBqJ0dxmD0HjLCSfhuxuW7uMoXsCR2i8fA+390QbRXBbzxF6RDB+G1cMSNyz+VU0+agZZ4edDP8wf96KWIbdsarmKsde3DMXn64e+2Eb6BYc/bjqiYx7c+ewRWFqzHd2/adQF6f5SrcQrLADbl3ViqxcJZrg=.APVD8g7HIfBB4EwXzKcReayihfNCUz5OvzUZDHxz4YfS"
    orders = get_don_hang(cooki)
    print_report(orders)
    # print(f"orders: {orders}")

if __name__ == "__main__":
    raise SystemExit(main())