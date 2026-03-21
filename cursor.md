# 🧠 Project Context (Bot_VPS)

Tài liệu này giúp AI/dev nắm nhanh repo — **cập nhật khi thêm lệnh, job type, hoặc đổi `job.result`.**

## 🎯 Mục tiêu

- Bot Telegram tự động hóa thao tác **Shopee** (lấy cookie/session `SPC_ST`, thông tin tài khoản, danh sách đơn buyer qua `checkmvd`) và **email tạm** (đọc inbox, nút chi tiết, xác minh link).
- Tách xử lý nặng/blocking ra **worker thread** qua **Job Queue**; handler async chỉ poll trạng thái job và gửi tin nhắn.

## 🧱 Tech Stack

| Thành phần | Công nghệ |
|------------|-----------|
| Ngôn ngữ | Python 3.x |
| Telegram | `python-telegram-bot` (`ApplicationBuilder`, `CommandHandler`, `CallbackQueryHandler`) |
| HTTP | `requests` (`login.py`, `email_*`, proxy); `urllib.request` (`checkmvd.py`) |
| Browser | Playwright sync (`verify_mail.py`) |
| Concurrency | `threading` + `queue.Queue` (job queue); `asyncio` trong handlers (polling, `asyncio.to_thread` cho `checkmvd.collect_orders`) |
| Local state | `proxy_keys.json` (`proxy_storage.py`); cache module-level `_email_cache` / `_email_creds` trong `commands.py` |

## 📦 Project Structure

| File / module | Vai trò |
|----------------|---------|
| `bot_tele.py` | Entry: `JobQueue(max_workers=10)`, đăng ký handlers `cvc`, `cks`, `checkmail`, `mailfree`, `setup_commands`, `run_polling`. |
| `commands.py` | Lệnh: `/cvc`, `/cks`, `/checkmail`, `/mailfree`, `/queue`, `/kipx`, `/vnpx`, `/delpx`; callback `email_*`; `check_job_status` (poll); sau `/cks` gọi `checkmvd.collect_orders` + `format_order_like_form`. |
| `job_queue.py` | `Job`, `add_job_if_no_active`, workers, `cleanup_old_jobs` / `start_cleanup_task`. |
| `workers.py` | `handle_cvc`, `handle_cks`, `handle_checkmail`, `handle_mailfree` — trả `dict` cho `check_job_status`. |
| `login.py` | Lấy `SPC_ST` + user info (HTTP giả lập client), dùng proxy khi có. |
| `checkmvd.py` | API đơn buyer Shopee: `collect_orders`, `build_stats`, format tiền/đơn. |
| `email_utils.py` | Inbox temp mail, format list/detail, nút inline, `process_mailfree`. |
| `email_api.py` | Client domain/register mail (`cheapluxurymail.xyz`). |
| `verify_mail.py` | Playwright mở URL verify (từ callback). |
| `proxy_storage.py` / `proxy.py` | Key proxy theo user, `get_user_best_proxy`, lưu key qua `/kipx`, `/vnpx`. |
| `testfuture.py` | Script thử HTTP (voucher Shopee) — **không** gắn bot. |

**Không có** `bot.py` trong repo; entry chính là **`python bot_tele.py`**.

## 🔌 API / External Services

### Shopee

- **Session:** `login.py` — lấy **`SPC_ST`** từ `Set-Cookie`, `extract_spc_st_and_user_info`, v.v.
- **Đơn buyer:** `checkmvd.py` — `get_all_order_and_checkout_list`, `get_order_detail`, tùy chọn logistics; dùng cookie dạng `SPC_ST=...`.

### Email tạm

- Domain/API qua `email_api.py` + đọc mail trong `email_utils.py`.

### Telegram

- Token hiện đặt trong `bot_tele.py` (nên chuyển **biến môi trường** — xem Current Tasks).

## 🔐 Security / Reverse Notes

- Repo **không** reverse native app; chủ yếu HTTP công khai + cookie/header giống client.
- Không commit: token bot, proxy keys, cookie người dùng.
- Playwright cần `playwright install` (Chromium) trên server.

## ⚙️ Core Logic

1. User gửi lệnh → `add_job_if_no_active(job_type, ...)` → worker chạy handler tương ứng trong `workers.py`.
2. `check_job_status` poll (sleep tăng dần tối đa ~5s) đến `completed`/`failed` — **không** còn giới hạn 30s cố định.
3. Kết quả: gửi HTML/text, inline keyboard (`has_buttons`, `inline_keyboard`); cache email theo `job_id`.
4. **`/cks`:** worker trả HTML + `store_creds` (`SPC_ST=...`) + **`proxies`** / **`proxy_source`** (cùng proxy `get_user_best_proxy` đã dùng cho login). Sau đó `check_job_status` gọi `collect_orders(..., proxies=...)` để API đơn Shopee đi qua **cùng proxy** (urllib `ProxyHandler`). Hiển thị tối đa **5 đơn** (`format_order_like_form`).
5. **Callback `email_*`:** inbox, refresh, chi tiết, verify — dùng `_email_cache` / `_email_creds`; verify qua `verify_mail` (thường thread/background).

## 🛡️ Anti-spam / hàng đợi

- **`add_job_if_no_active`:** trong một `lock`, nếu cùng `user_id` đã có job cùng **`job_type`** ở trạng thái **`pending` hoặc `processing`** → **không** tạo job mới (`None`).
- Cho phép user có **nhiều job type song song** (vd. một `cvc` và một `cks`), nhưng **không** spam cùng một lệnh khi job cũ chưa xong.
- **`max_workers=10`** (trong `bot_tele.py`): giới hạn song song toàn hệ thống.
- **Cleanup:** xóa job `completed`/`failed` cũ (mặc định giữ ~5 phút, chạy định kỳ).

## 🧪 Current Tasks (gợi ý)

- [ ] Đọc **`TOKEN`** từ biến môi trường (vd. `TELEGRAM_BOT_TOKEN`), không hardcode.
- [ ] Chuẩn hoá **`store_creds`** cho `/cks`: có thể dùng `dict` thống nhất với `/mailfree` (hiện worker trả **chuỗi** cookie).
- [ ] Giảm log/`print` nhạy cảm trong production.
- [ ] Đồng bộ README / `cursor.md` mỗi khi thêm lệnh hoặc đổi tham số `collect_orders`.

## ⚠️ Rules / Constraints

- **Một job active / user / `job_type`** (atomic trong `job_queue`).
- **Blocking** (HTTP lâu, Playwright, `checkmvd`) — trong worker thread hoặc `asyncio.to_thread`, không chặn event loop.
- **Proxy:** worker Shopee nên qua `get_user_best_proxy(user_id)`; key lưu bằng `/kipx`, `/vnpx`, xóa `/delpx`.
- **Callback:** `await query.answer()` sớm; cache email hết hạn → user gọi lại `/checkmail` hoặc lệnh tạo job mới.

## 🧩 Notes

- `checkmvd` CLI/`parse_args` — khi gọi từ bot dùng **`collect_orders(...)`** trực tiếp với tham số rõ.
- Cài dependency: `pip install -r requirements.txt` và cài browser Playwright nếu dùng verify.
