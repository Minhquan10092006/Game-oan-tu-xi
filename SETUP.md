# Hướng dẫn cài đặt — Hệ thống chấm bài AI Python

> Tài liệu này mô tả luồng Judge0 cũ. Bản K71 hiện hành dùng [README](README.md) và [hướng dẫn chạy giải](docs/HUONG_DAN_CHAY_GIAI.md); demo không chạy file nộp trong web.

## Sơ đồ kiến trúc

```
[Người dùng nộp code Python]
         │
         ▼
[Django REST API]  ─── POST /api/submissions/
         │
         ├─► [Kiểm tra kích thước & format code]
         │
         ▼
[Judge0 API]  ─── Thực thi code Python trong sandbox
         │
         ▼
[Django nhận stdout/stderr]
         │
         ├─► [Bộ chấm bài - judge/grader.py]
         │       ├─ Nhóm 1: Execution (code chạy được không?)
         │       ├─ Nhóm 2: Protocol (output đúng JSON schema?)
         │       ├─ Nhóm 3: Legal Move (engine xác nhận hợp lệ)
         │       ├─ Nhóm 4: Runtime Limit (không vượt thời gian)
         │       ├─ Nhóm 5: Robustness (xử lý edge cases)
         │       └─ Nhóm 6: Simulation (chơi thực trong ván thử)
         │
         ▼
[Lưu kết quả vào SQLite]
         │
         ▼
[Trả điểm số + chi tiết về frontend]
```

---

## Yêu cầu hệ thống

- **Python**: 3.10+ (project dùng 3.15)
- **Windows**: Đã test trên Windows 10/11

---

## Cài đặt

### 1. Clone repository

```cmd
git clone https://github.com/Minhquan10092006/Game-oan-tu-xi.git
cd Game-oan-tu-xi
```

### 2. Tạo virtual environment (nếu chưa có)

```cmd
python -m venv venv
```

### 3. Kích hoạt venv

```cmd
venv\Scripts\activate
```

### 4. Cài đặt Python packages

```cmd
python -m pip install -r requirements.txt
```

### 5. Tạo file .env từ .env.example

```cmd
copy .env.example .env
```

Mở `.env` và chỉnh sửa:

```env
DJANGO_SECRET_KEY=thay-bang-key-ngau-nhien-dai-hon-50-ky-tu
DJANGO_DEBUG=True
JUDGE0_BASE_URL=https://ce.judge0.com
JUDGE0_API_KEY=
```

> **Lưu ý về Judge0 API Key:**  
> Instance công khai `ce.judge0.com` không cần API key.  
> Nếu dùng instance riêng hoặc RapidAPI, thêm key vào `JUDGE0_API_KEY`.

### 6. Tạo database và chạy migrations

```cmd
python manage.py migrate
```

### 7. Tạo superuser (để vào admin panel)

```cmd
python manage.py createsuperuser
```

### 8. Chạy Django server (hỗ trợ cả HTTP & WebSocket)

```cmd
python manage.py runserver
```

Django (Daphne ASGI) sẽ chạy tại: http://localhost:8000
Cả chế độ 2 người, 8 người multiplayer realtime và spectator đều chạy trực tiếp trên Django server này.

---

## Cấu hình Judge0

### Sử dụng instance công khai (ce.judge0.com)

Không cần cấu hình thêm. Chỉ cần:

```env
JUDGE0_BASE_URL=https://ce.judge0.com
JUDGE0_API_KEY=
```

Giới hạn của instance công khai:
- Có thể bị rate limit khi quá nhiều request
- SLA không đảm bảo uptime 100%
- Không hỗ trợ đặt cpu_time_limit tùy ý (hệ thống sẽ tự retry không có limits)

### Kiểm tra trạng thái Judge0

Đăng nhập admin, sau đó gọi:

```
GET http://localhost:8000/api/judge/status/
```

Endpoint này chỉ dành cho admin (superuser).

### Sử dụng instance Judge0 tự triển khai

Nếu muốn tự deploy Judge0 (không bắt buộc):

```env
JUDGE0_BASE_URL=http://localhost:2358
JUDGE0_API_KEY=your-auth-token-if-configured
```

---

## Chạy tests

```cmd
python manage.py test matches judge submissions web --verbosity=2
```

Kết quả mong đợi: **76 tests passed**.

---

## Sử dụng API

### Đăng nhập (lấy session)

Django dùng session authentication. Đăng nhập qua trình duyệt tại `/admin/` hoặc dùng Basic Auth trong API client.

### Nộp bài AI

```http
POST /api/submissions/
Authorization: Basic <username:password base64>
Content-Type: application/json

{
    "ai_name": "MyGreedyAI",
    "source_code": "import sys, json\n..."
}
```

Response:
```json
{
    "id": 1,
    "submitter_username": "alice",
    "ai_name": "MyGreedyAI",
    "version": 1,
    "status": "completed",
    "score": 85.5,
    "submitted_at": "2026-10-12T12:00:00Z",
    ...
}
```

### Xem kết quả chấm chi tiết

```http
GET /api/submissions/1/result/
Authorization: Basic <credentials>
```

### Tạo trận đấu AI vs AI

```http
POST /api/matches/
Content-Type: application/json

{
    "player1_name": "AI Alpha",
    "player2_name": "AI Beta",
    "ai1_id": 1,
    "ai2_id": 2,
    "max_turns": 200
}
```

### Yêu cầu AI đề xuất nước đi

```http
POST /api/matches/1/ai-move/
Content-Type: application/json

{
    "player": 1,
    "submission_id": 1
}
```

---

## Viết AI Python

### Cấu trúc tối thiểu

```python
import sys, json

def main():
    data = json.loads(sys.stdin.read())
    legal_moves = data.get('legal_moves', [])
    
    if not legal_moves:
        print(json.dumps({"move": None}))
        return
    
    # Chọn nước đi đầu tiên (AI đơn giản nhất)
    move = legal_moves[0]
    print(json.dumps({
        "move": {
            "from_row": move["from_row"],
            "from_col": move["from_col"],
            "to_row": move["to_row"],
            "to_col": move["to_col"]
        }
    }))

if __name__ == '__main__':
    main()
```

### File mẫu đầy đủ

Xem file `ai_sample.py` trong repository.

### Kiểm tra AI cục bộ trước khi nộp

```cmd
python ai_sample.py < test_input.json
```

Tạo `test_input.json`:
```json
{
    "board": [[null, null, null, null, null, null, null, null, null],
              [null, null, null, null, null, null, null, null, null],
              [{"player": 1, "type": "rock", "id": "p1-rock-0"}, null, null, null, null, null, null, null, null],
              [null, null, null, null, null, null, null, null, null],
              [null, null, null, null, null, null, null, null, null],
              [null, null, null, null, null, null, null, null, null],
              [null, null, null, null, null, null, null, null, null],
              [null, null, null, null, null, null, null, null, null],
              [null, null, null, null, null, null, null, null, null]],
    "current_player": 1,
    "turn_number": 1,
    "legal_moves": [
        {"from_row": 2, "from_col": 0, "to_row": 3, "to_col": 0,
         "is_capture": false, "captured_type": null}
    ],
    "goal": {"row": 8, "col": 8},
    "opponent_goal": {"row": 0, "col": 0},
    "game_over": false
}
```

---

## Demo trận đấu

### Chạy demo qua Python shell

```cmd
python manage.py shell
```

```python
from matches.engine import GameState, build_ai_input, parse_ai_output, validate_ai_move
import json

# Tạo game mới
state = GameState()

# Xem input AI sẽ nhận
ai_input = build_ai_input(state)
print(f"Số nước đi hợp lệ: {len(ai_input['legal_moves'])}")
print(f"Lượt: Player {ai_input['current_player']}")

# Giả lập AI chọn nước đầu tiên
first_move = ai_input['legal_moves'][0]
mock_output = json.dumps({"move": first_move})

# Parse và validate
move = parse_ai_output(mock_output)
result = validate_ai_move(state, move)
print(f"Hợp lệ: {result['valid']}")

# Thực thi
if result['valid']:
    record = state.execute_move(move['from_row'], move['from_col'],
                                move['to_row'], move['to_col'])
    print(f"Nước đi: {record}")
```

---

## Danh sách file đã thêm/sửa

### Files mới tạo

| File | Mô tả |
|------|-------|
| `submissions/__init__.py` | App package |
| `submissions/apps.py` | App config |
| `submissions/models.py` | Model Submission, JudgeResult |
| `submissions/serializers.py` | DRF serializers |
| `submissions/views.py` | API views |
| `submissions/urls.py` | URL routing |
| `submissions/admin.py` | Admin panel |
| `submissions/tests.py` | Tests (API + grader) |
| `submissions/migrations/0001_initial.py` | DB migration |
| `judge/__init__.py` | App package |
| `judge/apps.py` | App config |
| `judge/client.py` | Judge0 HTTP client |
| `judge/grader.py` | Bộ chấm bài 6 nhóm |
| `judge/models.py` | (trống, dùng submissions model) |
| `judge/views.py` | Status endpoint |
| `judge/urls.py` | URL routing |
| `judge/tests.py` | Tests Judge0 client |
| `matches/__init__.py` | App package |
| `matches/apps.py` | App config |
| `matches/engine.py` | Python port của engine.js |
| `matches/models.py` | Model Match, MatchMove |
| `matches/serializers.py` | DRF serializers |
| `matches/views.py` | API views |
| `matches/urls.py` | URL routing |
| `matches/admin.py` | Admin panel |
| `matches/tests.py` | Tests engine + API |
| `matches/migrations/0001_initial.py` | DB migration |
| `ai_sample.py` | AI mẫu Python |
| `.env.example` | Template biến môi trường |
| `requirements.txt` | Python dependencies |
| `SETUP.md` | File này |

### Files đã sửa

| File | Thay đổi |
|------|----------|
| `config/settings.py` | Thêm apps mới, CORS, DRF, Judge0 config, dotenv |
| `config/urls.py` | Thêm API routes |
| `config/exception_handler.py` | **Mới** — custom error handler |

### Files KHÔNG thay đổi (giữ nguyên game)

- `server/engine.js` — game engine JS
- `server/index.js` — Socket.IO server
- `server/roomManager.js` — room manager
- `web/static/web/js/*.js` — frontend JS
- `web/static/web/css/*.css` — frontend CSS
- `web/templates/web/index.html` — game UI

---

## Những phần chưa tích hợp

1. **Celery task queue**: Hiện tại chấm bài chạy synchronous trong request.
   Trong production nên dùng Celery + Redis để chấm bất đồng bộ.

2. **WebSocket notify**: Khi chấm xong không tự notify frontend — frontend phải poll.

3. **Rate limiting per-IP**: Hiện tại kiểm tra qua settings nhưng chưa implement
   middleware tự động block. Cần thêm `django-ratelimit` hoặc nginx.

4. **AI vs AI auto-play**: Endpoint `/ai-move/` cho phép gọi từng lượt một.
   Chưa có endpoint chạy toàn bộ trận đấu tự động.

5. **Leaderboard**: Chưa có endpoint xếp hạng AI theo điểm số.
