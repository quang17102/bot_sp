from __future__ import annotations

import time
from playwright.sync_api import sync_playwright


def verify_link(url: str, wait_seconds: int = 8, headless: bool = True) -> None:
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
                "--window-size=1366,768",
            ],
        )
        print("Opening URL:", url)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        print("Page loaded:", page.url)
        time.sleep(wait_seconds)
        content = page.content()
        print(content)
        browser.close()
        print("DONE")


if __name__ == "__main__":
    # Test nhanh
    verify_link("https://vn.shp.ee/dlink/0taiae06", wait_seconds=5)
    print("Verify done")