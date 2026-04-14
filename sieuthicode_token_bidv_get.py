# -*- coding: utf-8 -*-
"""GET https://sieuthicode.com/historyapivcb/<token>"""
import argparse
import os

import requests

URL = "https://sieuthicode.com/historyapivcb/"


def get_token_bidv(token: str, *, timeout: float = 30.0) -> requests.Response:
    tok = (token or "").strip()
    return requests.get(URL + tok, timeout=timeout)


def main() -> None:
    p = argparse.ArgumentParser(description="GET TokenBIDV history API")
    p.add_argument(
        "token",
        nargs="?",
        default=os.environ.get("SIEUTHICODE_BIDV_TOKEN", ""),
        help="TokenBIDV value (or env SIEUTHICODE_BIDV_TOKEN)",
    )
    args = p.parse_args()
    tok = (args.token or "").strip()
    if not tok:
        p.error("missing token: pass arg or set SIEUTHICODE_BIDV_TOKEN")
    r = get_token_bidv(tok)
    print(r.status_code)
    print(r.text)


if __name__ == "__main__":
    main()
