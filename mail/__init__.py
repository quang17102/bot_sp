# -*- coding: utf-8 -*-
"""
Temp mail (cheapluxurymail): API đăng ký, đọc inbox, format Telegram, xác minh link.

- ``mail.api`` — domain + register
- ``mail.utils`` — login inbox, format list/detail, nút inline, ``process_mailfree``
- ``mail.verify`` — Playwright mở URL verify
"""

from . import api
from . import utils
from . import verify

__all__ = ["api", "utils", "verify"]
