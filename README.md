# Telegram Bot với Job Queue System

Hệ thống bot Telegram được xây dựng với kiến trúc Job Queue và Worker pattern để xử lý các tác vụ bất đồng bộ, đảm bảo bot không bị block khi xử lý các operations mất thời gian.

## 📋 Mục lục

- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Cấu trúc file](#cấu-trúc-file)
- [Luồng hoạt động](#luồng-hoạt-động)
- [Tính năng](#tính-năng)
- [Cài đặt và sử dụng](#cài-đặt-và-sử-dụng)
- [API Reference](#api-reference)
- [Best Practices](#best-practices)

## 🏗️ Kiến trúc hệ thống

```
┌─────────────┐
│   User      │
│  Telegram   │
└──────┬──────┘
       │ /cvc command
       ↓
┌─────────────────────────────────────┐
│         bot_tele.py                │
│  ┌──────────────────────────────┐  │
│  │  Telegram Bot Application    │  │
│  │  - Nhận commands từ user     │  │
│  │  - Đăng ký command handlers  │  │
│  └──────────┬───────────────────┘  │
│             │                       │
│  ┌──────────▼───────────────────┐  │
│  │      commands.py             │  │
│  │  - cvc_command()             │  │
│  │  - queue_status()            │  │
│  │  - check_job_status()        │  │
│  └──────────┬───────────────────┘  │
└─────────────┼───────────────────────┘
              │ Tạo job
              ↓
┌─────────────────────────────────────┐
│         job_queue.py                │
│  ┌──────────────────────────────┐  │
│  │      JobQueue                 │  │
│  │  - add_job_if_no_active()     │  │
│  │  - Atomic operation           │  │
│  │  - Race condition protection  │  │
│  │  - Cleanup old jobs           │  │
│  └──────────┬───────────────────┘  │
│             │                       │
│  ┌──────────▼───────────────────┐  │
│  │    Queue (FIFO)              │  │
│  │  - Pending jobs              │  │
│  └──────────┬───────────────────┘  │
└─────────────┼───────────────────────┘
              │ Worker lấy job
              ↓
┌─────────────────────────────────────┐
│      Workers (Threads)              │
│  ┌──────────┐  ┌──────────┐        │
│  │Worker 1 │  │Worker 2 │ ...     │
│  └────┬────┘  └────┬────┘        │
│       │             │              │
│  ┌────▼─────────────▼──────┐       │
│  │      workers.py         │       │
│  │  - handle_cvc()         │       │
│  │  - Xử lý blocking ops   │       │
│  └──────────┬──────────────┘       │
└─────────────┼───────────────────────┘
              │ Trả về result
              ↓
┌─────────────────────────────────────┐
│      Job Status Update               │
│  - status: completed/failed          │
│  - result: {...}                     │
└──────────┬──────────────────────────┘
           │
           ↓
┌─────────────────────────────────────┐
│   check_job_status() (Async Task)   │
│  - Polling job status                │
│  - Gửi kết quả về user              │
└─────────────────────────────────────┘
```

## 📁 Cấu trúc file

```
BotSp/
├── bot_tele.py          # Main file - Khởi tạo bot và job queue
├── commands.py          # Command handlers - Xử lý commands từ user
├── job_queue.py         # Job Queue System - Quản lý jobs và workers
├── workers.py           # Worker handlers - Xử lý các loại job
└── README.md           # Tài liệu hệ thống
```

### Chi tiết các file:

#### `bot_tele.py`
- **Chức năng**: Entry point của bot
- **Nhiệm vụ**:
  - Khởi tạo JobQueue
  - Đăng ký worker handlers
  - Khởi động workers và cleanup task
  - Tạo Telegram Application
  - Đăng ký command handlers

#### `commands.py`
- **Chức năng**: Xử lý commands từ user
- **Nhiệm vụ**:
  - `cvc_command()`: Handler cho `/cvc` command
  - `queue_status()`: Hiển thị trạng thái queue
  - `check_job_status()`: Polling và gửi kết quả về user
  - `setup_commands()`: Đăng ký handlers với dependencies

#### `job_queue.py`
- **Chức năng**: Quản lý Job Queue System
- **Nhiệm vụ**:
  - `Job`: Dataclass đại diện cho một job
  - `JobQueue`: Quản lý queue, workers, và jobs
  - `add_job_if_no_active()`: Atomic operation để tạo job
  - `cleanup_old_jobs()`: Xóa jobs cũ định kỳ
  - `start_cleanup_task()`: Chạy cleanup định kỳ

#### `workers.py`
- **Chức năng**: Worker handlers xử lý jobs
- **Nhiệm vụ**:
  - `handle_cvc()`: Xử lý job type "cvc"
  - Trả về result để `check_job_status` gửi về user

## 🔄 Luồng hoạt động

### Luồng xử lý command `/cvc`:

```
1. User gửi: /cvc hello
   ↓
2. cvc_command() nhận request
   ↓
3. Atomic operation: add_job_if_no_active()
   ├── Check: User có job đang chạy?
   │   ├── CÓ → Return None (chặn spam)
   │   └── KHÔNG → Tạo job mới
   ↓
4. Job được đưa vào queue
   ├── status: "pending"
   ├── data: {"input": "hello", "args": ["hello"]}
   ↓
5. Worker nhận job từ queue
   ├── status: "processing"
   ├── Gọi handle_cvc(job)
   ├── Xử lý (20 giây)
   └── status: "completed"
   ↓
6. check_job_status() polling
   ├── Phát hiện job.status == "completed"
   └── Gửi message về user: "✅ Hoàn thành!\nHello, bạn đã gửi: hello"
```

### Luồng chống spam:

```
User spam /cvc:
  Request 1: add_job_if_no_active()
    🔒 Lock → Check: No job → Create job1 → Release lock
  
  Request 2: add_job_if_no_active()
    🔒 Lock → Check: Has job1! → Return None (chặn)
  
  Request 3: add_job_if_no_active()
    🔒 Lock → Check: Has job1! → Return None (chặn)
```

## ✨ Tính năng

### 1. **Job Queue System**
- Xử lý bất đồng bộ với Worker pattern
- Không block bot khi xử lý operations mất thời gian
- Hỗ trợ nhiều workers xử lý song song

### 2. **Race Condition Protection**
- **Atomic Operation**: `add_job_if_no_active()` - Check + Create trong cùng lock
- Đảm bảo thread-safe khi nhiều requests đồng thời
- Không có gap giữa check và create

### 3. **Chống Spam**
- Mỗi user chỉ có 1 job đang chạy (pending/processing)
- Tự động chặn requests mới khi đã có job đang chạy
- Hiển thị thông tin job đang chạy cho user

### 4. **Auto Cleanup**
- Tự động xóa jobs cũ đã completed/failed
- Cleanup định kỳ mỗi 60 giây
- Xóa jobs cũ hơn 5 phút (có thể cấu hình)
- Tránh memory leak và performance degradation

### 5. **Job Status Tracking**
- Theo dõi trạng thái: `pending` → `processing` → `completed`/`failed`
- Polling mechanism để gửi kết quả về user
- Timeout handling (30 giây)

## 🚀 Cài đặt và sử dụng

### Yêu cầu:

```bash
python-telegram-bot>=20.0
```

### Cài đặt:

```bash
pip install -r requirements.txt
```

### Chạy bot:

```bash
python bot_tele.py
```

### Sử dụng:

```
/cvc [args]     - Gửi command cvc với arguments
/mailfree       - Tạo job mailfree (message rỗng)
/queue          - Xem trạng thái queue
```

## 📚 API Reference

### `JobQueue`

#### `__init__(max_workers: int = 3)`
Khởi tạo JobQueue với số lượng workers.

#### `add_job_if_no_active(job_type: str, user_id: int, chat_id: int, data: Dict[str, Any]) -> Optional[str]`
**Atomic operation** để tạo job chỉ khi user không có job đang chạy.

- **Returns**: `job_id` nếu tạo thành công, `None` nếu user đã có job đang chạy
- **Thread-safe**: Check + Create trong cùng lock

#### `cleanup_old_jobs(max_age_seconds: int = 300) -> int`
Xóa jobs cũ đã completed/failed.

- **max_age_seconds**: Thời gian tối đa giữ jobs cũ (mặc định 5 phút)
- **Returns**: Số lượng jobs đã xóa

#### `start_cleanup_task(interval_seconds: int = 60, max_age_seconds: int = 300)`
Bắt đầu task cleanup định kỳ.

- **interval_seconds**: Khoảng thời gian giữa các lần cleanup (mặc định 60s)
- **max_age_seconds**: Thời gian tối đa giữ jobs cũ (mặc định 300s)

#### `has_active_job_for_user(user_id: int, job_type: str = None) -> bool`
Kiểm tra xem user có job đang chạy không.

#### `get_active_job_for_user(user_id: int, job_type: str = None) -> Optional[Job]`
Lấy job đang chạy của user.

### `Job`

```python
@dataclass
class Job:
    job_id: str
    job_type: str
    user_id: int
    chat_id: int
    data: Dict[str, Any]
    created_at: datetime
    status: str  # "pending" | "processing" | "completed" | "failed"
    result: Optional[Dict[str, Any]]
    error: Optional[str]
```

## 🎯 Best Practices

### 1. **Thêm command mới**

```python
# 1. Thêm handler vào workers.py
def handle_new_command(job: Job) -> Dict[str, Any]:
    # Xử lý job
    return {"status": "success", "message": "..."}

# 2. Thêm command handler vào commands.py
async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                      job_queue: JobQueue, bot_app: 'Application'):
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    job_id = job_queue.add_job_if_no_active(
        job_type="new_command",
        user_id=user_id,
        chat_id=chat_id,
        data={...}
    )
    
    if job_id is None:
        # Chặn spam
        return
    
    # Tạo check_job_status task
    asyncio.create_task(check_job_status(chat_id, job_id, job_queue, bot_app))

# 3. Đăng ký trong bot_tele.py
job_queue.register_handler("new_command", handle_new_command)
setup_commands(application, job_queue)  # Tự động đăng ký
```

### 2. **Truyền dữ liệu từ context vào worker**

```python
# Trong command handler
args = context.args
job_id = job_queue.add_job_if_no_active(
    job_type="cvc",
    user_id=user_id,
    chat_id=chat_id,
    data={
        "input": args[0] if args else None,
        "args": args,
        "user_data": context.user_data,
    }
)

# Trong worker handler
def handle_cvc(job: Job) -> Dict[str, Any]:
    input_data = job.data.get("input")
    args = job.data.get("args", [])
    # Xử lý...
```

### 3. **Xử lý lỗi trong worker**

```python
def handle_cvc(job: Job) -> Dict[str, Any]:
    try:
        # Xử lý
        return {"status": "success", "message": "..."}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

### 4. **Cấu hình cleanup**

```python
# Trong bot_tele.py
job_queue.start_cleanup_task(
    interval_seconds=30,  # Cleanup mỗi 30s
    max_age_seconds=180   # Xóa jobs cũ hơn 3 phút
)
```

## 🌐 Proxy & `get_user_best_proxy`

- **Mục tiêu**: chọn proxy tốt nhất cho từng user dựa trên các key đã lưu trong `proxy_keys.json`, được set thông qua các command như `/kipx` (KiotProxy) và `/vnpx` (VNProxy / proxyxoay).
- **API chính**: `get_user_best_proxy(user_id: int) -> Tuple[Optional[Dict[str, str]], Optional[str]]` (trong `proxy_storage.py`).

### Hành vi chi tiết

- **Input**: `user_id` (Telegram user id).
- **Output**: tuple `(proxies, source)`:
  - `proxies`: 
    - `None` nếu không có proxy phù hợp.
    - Hoặc dict dạng `{"http": "...", "https": "..."}` (đã chuẩn hóa scheme `http://` nếu thiếu).
  - `source`:
    - `"kiot_expired"`: key KiotProxy của user đã hết hạn (từ `get_proxy_kiotproxy`).
    - `"vnpx"`: đang dùng VNProxy (proxyxoay) vừa lấy mới từ API bằng key `vnpx`.
    - `"vnpx_cached"`: đang dùng VNProxy lấy từ cache `vnpx_proxy` (được lưu từ lần thành công trước đó).
    - `None`: không có proxy phù hợp.

### Logic lựa chọn (phiên bản hiện tại)

- **Bước 1 – Đọc dữ liệu user**
  - Đọc toàn bộ file `proxy_keys.json` qua `_load_all()`.
  - Lấy map tương ứng user: `user_map = data.get(str(user_id)) or {}`.

- **Bước 2 – Kiểm tra KiotProxy (ưu tiên)**
  - Lấy `kiot_key = user_map.get("kiot")`.
  - Nếu có `kiot_key` và module `proxy` khả dụng (hàm `get_proxy_kiotproxy` tồn tại):
    - Gọi `result = get_proxy_kiotproxy(kiot_key)`.
    - Nếu `result == "KEY_EXPIRED"` → trả về `(None, "kiot_expired")`.
    - Nếu `result` là dict proxy hợp lệ → chuẩn hóa các value:
      - Nếu đã bắt đầu bằng `http://` hoặc `https://` → giữ nguyên.
      - Nếu không → tự động thêm `http://` phía trước.
    - (Lưu ý: logic check `_is_proxy_live` cho KiotProxy hiện tại đang được tối giản, có thể bổ sung sau nếu cần.)

- **Bước 3 – VNProxy (proxyxoay) + cache**
  - Lấy:
    - `vn_key = user_map.get("vnpx")` – API key proxyxoay do `/vnpx` lưu.
    - `vn_cached = user_map.get("vnpx_proxy")` – giá trị `ip:port` proxy đã cache (nếu có).
  - **3a. Call API lấy proxy mới**
    - Nếu có `vn_key` và `get_proxy_proxyxoay` khả dụng:
      - Gọi `result = get_proxy_proxyxoay(vn_key)`.
      - Nếu `result` là dict và có dữ liệu:
        - Chuẩn hóa thành `formatted` (tự thêm `http://` nếu thiếu).
        - Trả về `(formatted, "vnpx")`.
  - **3b. Dùng proxy VN đã cache**
    - Nếu `vn_cached` tồn tại:
      - Tạo dict:
        - `cached = {"http": f"http://{ip_port}", "https": f"http://{ip_port}"}`.
      - Gọi `_is_proxy_live(cached)`:
        - Nếu live → trả về `(cached, "vnpx_cached")`.

- **Bước 4 – Không có proxy**
  - Nếu tất cả các nhánh trên không return → trả `(None, None)`.

Hàm này được dùng tại `workers.py` (ví dụ trong `handle_cks`) để worker chỉ cần gọi một lần và nhận về proxy tốt nhất mà không phải tự xử lý thứ tự ưu tiên, check live hay cache.

## 🔒 Thread Safety

Hệ thống đảm bảo thread-safe với:

1. **Lock mechanism**: Tất cả operations trên `self.jobs` đều có lock
2. **Atomic operations**: Check + Create trong cùng lock
3. **Queue thread-safe**: Python `queue.Queue` là thread-safe

## 📊 Performance

- **Concurrent processing**: Nhiều workers xử lý song song
- **Non-blocking**: Bot không bị block khi xử lý jobs
- **Auto cleanup**: Tránh memory leak và performance degradation
- **Efficient checking**: O(n) với n là số jobs đang active

## 🐛 Troubleshooting

### Bot không phản hồi
- Kiểm tra workers có đang chạy không
- Kiểm tra queue có bị đầy không
- Xem logs để tìm lỗi

### Jobs không được xử lý
- Kiểm tra handler đã được đăng ký chưa
- Kiểm tra workers có đang chạy không
- Xem logs của workers

### Memory tăng cao
- Kiểm tra cleanup task có đang chạy không
- Điều chỉnh `max_age_seconds` nếu cần
- Kiểm tra có jobs nào bị stuck không

## 📝 License

MIT License

## 👥 Contributors

- Developer: [Your Name]

---

**Lưu ý**: Đây là hệ thống bot được thiết kế với kiến trúc hiện đại, đảm bảo thread-safe, chống spam, và tự động cleanup để đảm bảo performance tốt nhất.

