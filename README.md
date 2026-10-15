# ⚔️ Oẳn Tù Tì 2.0

Game cờ chiến thuật dựa trên luật Oẳn Tù Tì — chơi local, online 8 người, nộp AI Python và bảng xếp hạng ELO.

🌐 **Demo trực tuyến:** https://game-oan-tu-xi.onrender.com

---

## Mục lục

- [Luật chơi](#luật-chơi)
- [Chế độ chơi](#chế-độ-chơi)
- [Cài đặt](#cài-đặt)
- [Chạy game](#chạy-game)
- [Deploy lên Render](#deploy-lên-render)
- [Truy cập database](#truy-cập-database)
- [Hệ thống AI Judge](#hệ-thống-ai-judge)
- [Hệ thống ELO](#hệ-thống-elo)
- [Chế độ Người xem](#chế-độ-người-xem-spectator)
- [Cấu trúc dự án](#cấu-trúc-dự-án)
- [API Reference](#api-reference)
- [Chạy tests](#chạy-tests)

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
| **AI Battle** | Cho 2 bot AI đấu nhau trực tiếp | Django (port 8000) |
| **Ranking** | Bảng xếp hạng ELO toàn server | Django (port 8000) |

---

## Cài đặt

### Yêu cầu

- Python 3.10+ (đã test trên 3.12 và 3.15)
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

```cmd
venv\Scripts\activate
python manage.py runserver
```
→ Truy cập: http://localhost:8000

> Hệ thống sử dụng Daphne và Django Channels phục vụ cả HTTP lẫn WebSocket trên port 8000. Không cần Node.js server riêng.

### Các trang chính

| URL | Mô tả |
|-----|-------|
| http://localhost:8000 | Menu chính (đăng nhập / đăng ký / chơi ngay) |
| http://localhost:8000/ai/ | Trang nộp AI |
| http://localhost:8000/ai-battle/ | Cho 2 bot AI đấu nhau |
| http://localhost:8000/battlecode/ | Demo chế độ Battlecode |
| http://localhost:8000/ranking/ | Bảng xếp hạng ELO |
| http://localhost:8000/history/ | Lịch sử trận đấu |
| http://localhost:8000/season-admin/ | Quản lý mùa giải (admin) |
| http://localhost:8000/admin/ | Django Admin panel |

> **Lưu ý:** Đăng nhập, đăng ký và chơi thử khách (guest) đều thực hiện ngay trên trang chủ `/` — không có trang `/login/` hay `/register/` riêng.

---

## Deploy lên Render

Project đã có sẵn file cấu hình cho Render:

- `render.yaml` — cấu hình service và biến môi trường
- `build.sh` — script build (pip install, collectstatic, migrate)

### Các bước deploy

1. Push code lên GitHub
2. Vào [render.com](https://render.com) → **New** → **Blueprint**
3. Chọn repo → Render tự đọc `render.yaml` và tạo service
4. Thêm biến môi trường cần thiết (đặc biệt `DJANGO_SECRET_KEY`)

### Start command

```
daphne -b 0.0.0.0 -p $PORT config.asgi:application
```

> Render sử dụng `runtime: python` — không cần Node.js hay `package.json`.

---

## Truy cập database

Project dùng **SQLite** khi chạy local (`db.sqlite3` ở thư mục gốc), và **PostgreSQL** khi deploy trên Render (cấu hình qua `DATABASE_URL`).

### Cách 1 — Admin panel (dễ nhất, không cần cài thêm gì)

```
http://localhost:8000/admin/
```
Đăng nhập bằng tài khoản superuser. Xem/sửa/xóa trực tiếp trên trình duyệt.

Các bảng có thể quản lý:
- **Users** → danh sách người dùng
- **User profiles** → điểm ELO, thống kê thắng/thua
- **Seasons** → mùa giải
- **Match histories** → lịch sử trận đấu có replay
- **Submissions** → bài nộp AI và điểm
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

# Xem lịch sử trận đấu
from web.models import MatchHistory
MatchHistory.objects.order_by('-played_at')[:10].values('player__username', 'result', 'board_preset', 'played_at')
```

### Cách 3 — DB Browser for SQLite (GUI desktop)

1. Tải tại https://sqlitebrowser.org/dl/
2. Mở file `db.sqlite3` trong thư mục gốc project
3. Tab **Browse Data** → chọn bảng để xem

Các bảng quan trọng:

| Tên bảng | Nội dung |
|----------|----------|
| `auth_user` | Tài khoản người dùng |
| `web_userprofile` | ELO, wins, losses, draws |
| `web_season` | Mùa giải |
| `web_matchhistory` | Lịch sử trận đấu + replay data |
| `submissions_submission` | Bài nộp AI |
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

1. Đăng nhập tại trang chủ `/`
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
Thư mục **`bots/`** chứa các bot mẫu (`student1_bot.py`, `student2_bot.py`).

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
- Cập nhật tự động sau mỗi trận đấu
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
├── web/                     # Django app — giao diện & auth
│   ├── templates/web/
│   │   ├── index.html           # Menu chính + auth overlay + solo/multi UI
│   │   ├── ai_judge.html        # Trang nộp bài AI
│   │   ├── ai_battle.html       # Cho 2 bot đấu nhau
│   │   ├── battlecode_demo.html # Demo chế độ Battlecode
│   │   ├── ranking.html         # Bảng xếp hạng ELO
│   │   ├── history.html         # Lịch sử trận đấu
│   │   ├── match_detail.html    # Chi tiết + replay một trận
│   │   ├── season_admin.html    # Quản lý mùa giải
│   │   ├── admin_code_review.html # Duyệt code cộng đồng (admin)
│   │   ├── login.html           # (legacy, hiện dùng overlay trên index)
│   │   └── register.html        # (legacy, hiện dùng overlay trên index)
│   ├── static/web/js/
│   │   ├── game.js              # Game engine JS (solo mode)
│   │   ├── ui.js                # Render board UI
│   │   ├── screen-manager.js    # Quản lý màn hình
│   │   └── multiplayer.js       # Multiplayer + spectator (WebSocket)
│   ├── models.py            # UserProfile, ELO, Season, MatchHistory
│   ├── views.py             # Django views (auth + trang chính)
│   ├── consumers.py         # WebSocket consumers (Django Channels)
│   ├── room_manager.py      # Quản lý phòng chơi in-memory
│   ├── api_views.py         # Ranking API
│   ├── routing.py           # WebSocket URL routing
│   └── urls.py / api_urls.py
│
├── submissions/             # Django app — bài nộp AI
│   ├── models.py            # Submission, JudgeResult
│   ├── views.py             # CRUD API
│   └── serializers.py
│
├── judge/                   # Django app — chấm bài
│   ├── client.py            # Gọi Judge0 API
│   └── grader.py            # Bộ chấm 6 nhóm tiêu chí
│
├── matches/                 # Django app — trận đấu
│   ├── engine.py            # Game engine Python (đầy đủ luật)
│   ├── game_engine.py       # Game engine phiên bản thứ 2
│   ├── match_manager.py     # Quản lý vòng đời trận đấu
│   ├── bot_runner.py        # Chạy bot AI trong sandbox
│   ├── ai_battle.py         # Logic đấu AI vs AI
│   ├── demo_views.py        # Views demo/battlecode
│   ├── models.py            # Match, MatchMove
│   └── views.py             # API + ELO update
│
├── bots/                    # Bot mẫu Python
│   ├── student1_bot.py
│   └── student2_bot.py
│
├── config/                  # Django project config
│   ├── settings.py
│   ├── asgi.py              # ASGI entry point (Daphne + Channels)
│   ├── wsgi.py
│   └── urls.py
│
├── ai_sample.py             # AI mẫu Python (chiến lược greedy)
├── manage.py
├── db.sqlite3               # SQLite database (local)
├── requirements.txt         # Python dependencies
├── render.yaml              # Cấu hình deploy Render
├── build.sh                 # Script build cho Render
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
GET    /api/rooms/                 Danh sách phòng đang hoạt động
```

---

## Chạy tests

```cmd
venv\Scripts\activate
python manage.py test matches judge submissions web --verbosity=2
```

Kết quả mong đợi: **76 tests passed**.
