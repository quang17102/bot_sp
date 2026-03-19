from __future__ import annotations

import time
from playwright.sync_api import sync_playwright


def verify_link(url: str, wait_seconds: int = 5, headless: bool = True) -> None:
    """
    Mở link verify bằng Playwright.

    Args:
        url: link xác minh lấy từ email.
        wait_seconds: thời gian chờ sau khi load (để trang xử lý redirect/submit).
        headless: chạy không hiện browser.
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("verify_link: url rỗng")
    print("START VERIFY")
    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1366,768",
            ],
        )
        print("Opening URL:", url)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Ho_Chi_Minh",
            geolocation={"latitude": 16.0471, "longitude": 108.2062},
            permissions=["geolocation"],
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
        )
        page = context.new_page()
        page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        """)
        page.goto(url, wait_until="domcontentloaded")
        print("Page loaded:", page.url)

        time.sleep(wait_seconds)

        content = page.content()
        print(content)
        with open("page.html", "w", encoding="utf-8") as f:
            f.write(content)
        browser.close()
        print("DONE")


if __name__ == "__main__":
    # Test nhanh
    verify_link("https://vn.shp.ee/dlink/0taiae06", wait_seconds=5)
    print("Verify done")