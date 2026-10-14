# ⚔️ Oẳn Tù Tì 2.0

## Battlecode demo (không dùng Judge0)

Luồng demo mới chạy hai bot độc lập theo JSON stdin/stdout, kiểm tra nước đi hoàn toàn ở server và trả toàn bộ replay để frontend phát lại. Lõi luật ở `matches/game_engine.py`; runner ở `matches/bot_runner.py` và `matches/match_manager.py`.

Chạy kiểm thử luồng đầy đủ:

```bash
python manage.py test matches.tests_battlecode
```

API demo:

- `GET /api/matches/boards/` — các preset `classic_9x9`, `rectangle_7x11`, `cross_9x9`, `obstacles_9x9`.
- `POST /api/matches/demo/` (multipart) — `player1_file`, `player2_file`, tùy chọn `preset`, `max_plies`, `timeout`.
- `GET /api/matches/demo/{match_id}/` — metadata, events, snapshots và kết quả replay.
- `GET /api/matches/demo/{match_id}/state/` — snapshot cuối.

Chạy giao diện local:

```bash
python manage.py migrate
python manage.py runserver
```

Sau đó mở **http://127.0.0.1:8000/battlecode/**. Chọn hai file trong `bots/`, chọn preset, bấm **Bắt đầu trận**, rồi dùng Play/Pause, Step, Replay và chọn tốc độ để xem diễn biến. Màn hình này không yêu cầu đăng nhập.

Bot mẫu nằm trong `bots/student1_bot.py` và `bots/student2_bot.py`. Mỗi lượt bot nhận một JSON, rồi chỉ in một JSON `{ "move": {"piece_id", "from", "to"}, "userdata": ... }`. Tọa độ dùng `[row, col]` từ 1. Không ghi log ra stdout.

```bash
python bots/student1_bot.py < bots/sample_input.json
python bots/student2_bot.py < bots/sample_input.json
```

Game cờ chiến thuật dựa trên luật Oẳn Tù Tì — 4 chế độ: chơi local, online 8 người, nộp AI Python và bảng xếp hạng ELO.

---

## Mục lục

- [Luật chơi](#luật-chơi)
- [Chế độ chơi](#chế-độ-chơi)
- [Cài đặt](#cài-đặt)
- [Chạy game](#chạy-game)
- [Truy cập database](#truy-cập-database)
- [Hệ thống AI Judge](#hệ-thống-ai-judge)
- [Hệ thống ELO](#hệ-thống-elo)
- [Cấu trúc dự án](#cấu-trúc-dự-án)
- [API Reference](#api-reference)

---

## Luật chơi

Bàn cờ **9×9**. Mỗi người chơi có **9 quân**: 3 Búa 🪨, 3 Bao 📄, 3 Kéo ✂️.

| Di chuyển | Quân đi **1 ô theo 8 hướng** (như quân Vua trong cờ vua) |
|-----------|----------------------------------------------------------|
| Chiến đấu | Búa thắng Kéo · Kéo thắng Bao · Bao thắng Búa |
| Bị chặn   | Cùng loại với quân đối thủ → không đi vào được |
| Bị cản    | Quân đối thủ khắc chế quân của mình → không đi vào được |

**Điều kiện thắng** (một trong 3):
1. Đưa bất kỳ quân nào đến **ô đích** của đối thủ
   - Player 1 → ô (9,9) · Player 2 → ô (1,1)
2. **Loại hết** toàn bộ quân đối thủ
3. Đối thủ **không còn nước đi** hợp lệ (stalemate)

---

## Chế độ chơi

| Chế độ | Mô tả | Server |
|--------|-------|--------|
| **2 Người** | Chơi cùng máy, luân phiên lượt | Django (port 8000) |
| **8 Người** | 4 phòng đấu realtime qua WebSocket | Django Channels (port 8000) |
| **👁 Xem phòng** | Tối đa **10 người xem** mỗi phòng, realtime | Django Channels (port 8000) |
| **Nộp AI** | Viết Python, chấm qua Judge0 | Django (port 8000) |
| **Ranking** | Bảng xếp hạng ELO toàn server | Django (port 8000) |

---

## Cài đặt

### Yêu cầu

- Python 3.10+ (đã test trên 3.15)
- Kết nối internet (để gọi Judge0 API)

### Bước 1 — Clone

```cmd
git clone https://github.com/Minhquan10092006/Game-oan-tu-xi.git
cd Game-oan-tu-xi
```

### Bước 2 — Python packages

```cmd
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
```

### Bước 3 — Tạo file .env

```cmd
copy .env.example .env
```

Mở `.env`, sửa `DJANGO_SECRET_KEY` thành một chuỗi ngẫu nhiên dài (>50 ký tự):

```env
DJANGO_SECRET_KEY=abc123...thay-bang-chuoi-ngau-nhien-cua-ban
DJANGO_DEBUG=True
JUDGE0_BASE_URL=https://ce.judge0.com
JUDGE0_API_KEY=
```

### Bước 4 — Tạo database

```cmd
python manage.py migrate
```

### Bước 5 — Tạo tài khoản admin

```cmd
python manage.py createsuperuser
```

---

## Chạy game

Chỉ cần **1 terminal** duy nhất:

**Khởi chạy Django (Daphne ASGI + WebSocket + HTTP):**
```cmd
venv\Scripts\activate
python manage.py runserver
```
→ Truy cập: http://localhost:8000

> Hệ thống sử dụng Daphne và Django Channels phục vụ cả HTTP lẫn WebSocket trên port 8000, không cần chạy Node.js server riêng.

### Các trang chính

| URL | Mô tả |
|-----|-------|
| http://localhost:8000 | Menu chính |
| http://localhost:8000/register/ | Đăng ký tài khoản |
| http://localhost:8000/login/ | Đăng nhập |
| http://localhost:8000/ai/ | Trang nộp AI |
| http://localhost:8000/ranking/ | Bảng xếp hạng ELO |
| http://localhost:8000/admin/ | Admin panel |

---

## Truy cập database

Project dùng **SQLite** (`db.sqlite3` ở thư mục gốc). Có 4 cách xem và quản lý:

### Cách 1 — Admin panel (dễ nhất, không cần cài thêm gì)

```
http://localhost:8000/admin/
```
Đăng nhập bằng tài khoản superuser. Xem/sửa/xóa trực tiếp trên trình duyệt.

Các bảng có thể quản lý:
- **Users** → danh sách người dùng
- **User profiles** → điểm ELO, thống kê thắng/thua
- **Submissions** → bài nộp AI và điểm
- **Judge results** → kết quả chấm từng nhóm
- **Matches** → trận đấu
- **Match moves** → lịch sử nước đi

### Cách 2 — Django shell (truy vấn Python)

```cmd
venv\Scripts\activate
python manage.py shell
```

```python
# Xem tất cả người dùng
from django.contrib.auth.models import User
User.objects.all().values('id', 'username', 'date_joined')

# Xem bảng xếp hạng ELO
from web.models import UserProfile
UserProfile.objects.order_by('-elo').values('user__username', 'elo', 'wins', 'losses')

# Xem bài nộp gần nhất
from submissions.models import Submission
Submission.objects.order_by('-submitted_at')[:10].values('submitter__username', 'ai_name', 'status', 'score')

# Tổng số trận đã chơi
from matches.models import Match
Match.objects.filter(status='finished').count()

# Xem nước đi của một trận
from matches.models import MatchMove
MatchMove.objects.filter(match_id=1).values()
```

### Cách 3 — DB Browser for SQLite (GUI desktop)

1. Tải tại https://sqlitebrowser.org/dl/
2. Mở file `db.sqlite3` trong thư mục gốc project
3. Tab **Browse Data** → chọn bảng để xem

Các bảng quan trọng:

| Tên bảng | Nội dung |
|----------|----------|
| `auth_user` | Tài khoản người dùng |
| `web_userprofile` | ELO, wins, losses |
| `submissions_submission` | Bài nộp AI |
| `submissions_judgeresult` | Kết quả chấm chi tiết |
| `matches_match` | Trận đấu |
| `matches_matchmove` | Lịch sử nước đi |

### Cách 4 — SQLite CLI (dòng lệnh)

```cmd
sqlite3 db.sqlite3
```

```sql
-- Xem danh sách bảng
.tables

-- Xem cấu trúc bảng
.schema web_userprofile

-- Top 10 ELO
SELECT u.username, p.elo, p.wins, p.losses
FROM web_userprofile p
JOIN auth_user u ON p.user_id = u.id
ORDER BY p.elo DESC
LIMIT 10;

-- Bài nộp gần đây
SELECT u.username, s.ai_name, s.status, s.score, s.submitted_at
FROM submissions_submission s
JOIN auth_user u ON s.submitter_id = u.id
ORDER BY s.submitted_at DESC
LIMIT 10;

-- Thoát
.quit
```

> **Backup database:** copy file `db.sqlite3` ra nơi khác. Khôi phục bằng cách copy lại.

---

## Hệ thống AI Judge

### Quy trình

1. Đăng nhập tại `/login/` hoặc đăng ký tại `/register/`
2. Vào `/ai/` → viết code Python vào editor
3. Nhấn **Nộp bài & Chấm điểm** → Django gửi code lên Judge0
4. Kết quả hiện sau 20–60 giây

### Giao thức AI

AI nhận JSON từ **stdin**, in JSON ra **stdout**:

```python
import sys, json

data = json.loads(sys.stdin.read())
moves = data['legal_moves']   # danh sách nước đi hợp lệ

# Chọn nước đi từ danh sách legal_moves
m = moves[0]
print(json.dumps({
    "move": {
        "from_row": m["from_row"],
        "from_col": m["from_col"],
        "to_row":   m["to_row"],
        "to_col":   m["to_col"]
    }
}))
```

Xem file **`ai_sample.py`** để có ví dụ đầy đủ với chiến lược greedy.

### Tiêu chí chấm điểm (100 điểm)

| Nhóm | Điểm | Nội dung |
|------|------|----------|
| Thực thi | 15 | Code có chạy được không |
| Giao thức JSON | 20 | Output đúng định dạng |
| Nước đi hợp lệ | 30 | Game engine xác nhận |
| Giới hạn thời gian | 10 | Không vượt CPU limit |
| Độ bền | 10 | Xử lý edge cases không crash |
| Simulation | 15 | Chơi 20 lượt thử không đi sai |

### Cấu hình Judge0

Mặc định dùng instance công khai `https://ce.judge0.com` (miễn phí, có rate limit).

Để dùng instance riêng, sửa trong `.env`:
```env
JUDGE0_BASE_URL=http://your-judge0-server:2358
JUDGE0_API_KEY=your-token-if-needed
```

---

## Hệ thống ELO

- ELO khởi đầu: **1200**
- Hệ số K: **32**
- Cập nhật tự động sau mỗi trận đấu qua API `/api/matches/{id}/ai-move/`
- Xem bảng xếp hạng tại `/ranking/`

Công thức:
```
expected = 1 / (1 + 10^((opponent_elo - my_elo) / 400))
delta    = 32 × (1 − expected)
my_new_elo       = my_elo + delta
opponent_new_elo = opponent_elo − delta
```

---

## Chế độ Người xem (Spectator)

Trong chế độ **8 người**:

1. Nhập mã phòng và tên vào ô bên dưới
2. Nhấn **👁 Xem phòng** (thay vì "Vào phòng")
3. Bàn cờ hiện ra với banner "👁 Đang xem" — không thể đi nước
4. Số người xem hiển thị realtime ở góc mỗi ô (👁 2/10)
5. Tối đa **10 người xem** mỗi phòng

---

## Cấu trúc dự án

```
Game-oan-tu-xi/
│
├── web/                     # Django app — giao diện & multiplayer
│   ├── templates/web/
│   │   ├── index.html       # Menu + game solo + multi UI
│   │   ├── ai_judge.html    # Trang nộp bài AI
│   │   ├── ranking.html     # Bảng xếp hạng
│   │   ├── login.html       # Trang đăng nhập
│   │   └── register.html    # Trang đăng ký
│   ├── static/web/js/
│   │   ├── game.js          # Game engine JS (solo mode)
│   │   ├── ui.js            # Render board UI
│   │   ├── screen-manager.js
│   │   └── multiplayer.js   # Multiplayer realtime WebSocket
│   ├── room_manager.py      # Quản lý phòng chơi multiplayer (In-Memory)
│   ├── consumers.py         # Django Channels WebSocket Consumer
│   ├── routing.py           # WebSocket routing (/ws/multiplayer/)
│   ├── models.py            # UserProfile, ELO
│   ├── views.py             # Django views + /api/rooms/
│   ├── api_views.py         # Ranking API
│   └── urls.py / api_urls.py
│
├── submissions/             # Django app — bài nộp AI
│   ├── models.py            # Submission, JudgeResult
│   ├── views.py             # CRUD API
│   └── serializers.py
│
├── judge/                   # Django app — chấm bài
│   ├── client.py            # Gọi Judge0 API
│   └── grader.py            # Bộ chấm 6 nhóm
│
├── matches/                 # Django app — trận đấu
│   ├── engine.py            # Game engine logic Python
│   ├── models.py            # Match, MatchMove
│   └── views.py             # API + ELO update
│
├── config/                  # Django project config
│   ├── settings.py          # Daphne, Channels, DRF config
│   ├── asgi.py              # ProtocolTypeRouter (HTTP + WebSocket)
│   └── urls.py
│
├── ai_sample.py             # AI mẫu Python
├── manage.py
├── db.sqlite3               # SQLite database
├── requirements.txt         # Python dependencies
├── .env.example             # Template biến môi trường
└── README.md
```

---

## API Reference

Tất cả API yêu cầu đăng nhập (trừ `/api/ranking/`).

### Submissions

```
POST   /api/submissions/              Nộp bài AI mới
GET    /api/submissions/              Danh sách bài của tôi
GET    /api/submissions/{id}/         Chi tiết bài nộp
GET    /api/submissions/{id}/result/  Kết quả chấm chi tiết
```

### Matches

```
POST   /api/matches/               Tạo trận đấu
GET    /api/matches/{id}/          Chi tiết trận
POST   /api/matches/{id}/ai-move/  AI đề xuất nước đi
```

### Ranking & Judge

```
GET    /api/ranking/               Bảng xếp hạng ELO (công khai)
GET    /api/judge/status/          Trạng thái Judge0 (chỉ admin)
```

---

## Chạy tests

```cmd
venv\Scripts\activate
python manage.py test matches judge submissions web --verbosity=2
```

Kết quả mong đợi: **76 tests passed**.
