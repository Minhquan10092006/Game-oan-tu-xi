# TÀI LIỆU MÔ TẢ DỰ ÁN GAME OẲN TÙ TÌ 2.0 (K71)
**Dùng để bảo vệ dự án trước thầy cô và các bạn cùng lớp**

---

## 1. TỔNG QUAN DỰ ÁN

### 1.1 Tên dự án
**Oẳn Tù Tì 2.0 — Hệ thống Battlecode cho giải thi đấu K71**

### 1.2 Mô tả ngắn gọn
Hệ thống web cho phép sinh viên viết bot Python điều khiển quân cờ trên bàn 9×9 theo luật Kéo-Búa-Bao. Hệ thống tự động thực thi code sinh viên, kiểm tra nước đi hợp lệ, điều phối trận đấu và tổ chức giải thi đấu vòng tròn hai lượt với xếp hạng chuyên nghiệp.

### 1.3 Đối tượng sử dụng
- **Sinh viên K71**: Nộp bài Python, xem replay, luyện tập
- **Ban tổ chức (BTC)**: Khóa bài, chạy giải, xuất bảng xếp hạng, quản lý khiếu nại

### 1.4 Công nghệ chính
| Thành phần | Công nghệ |
|------------|-----------|
| Web Framework | Django 5.x + Django REST Framework |
| Game Engine | Python thuần túy (không phụ thuộc framework) |
| Sandbox chạy bot | Docker (container隔离, không root, giới hạn CPU/RAM/PIDs) |
| Database | SQLite (local), PostgreSQL (production qua DATABASE_URL) |
| Frontend | HTML/CSS/JS vanilla (responsive, không framework nặng) |
| Triển khai demo | Render Free Tier |

---

## 2. LUẬT CHƠI GAME (THEO THỂ LỆ K71-V1.0)

### 2.1 Bàn cờ và bố trí
- Bàn **9×9**, tọa độ (hàng, cột) từ **1 đến 9**
- Mỗi bên **9 quân**: 3 Kéo (scissors), 3 Búa (rock), 3 Bao (paper)
- **P1 đi trước**, đích P1 = (9,9), đích P2 = (1,1)

**Bố trí P1 (góc trên-trái 3×3):**
| Hàng 1 | Kéo | Búa | Bao |
|--------|-----|-----|-----|
| Hàng 2 | Bao | Kéo | Búa |
| Hàng 3 | Búa | Bao | Kéo |

**P2**: Đối xứng 180° (quay ngược bàn cờ)

### 2.2 Di chuyển và bắt quân
- Mỗi nước: **1 quân đi 1 ô** theo 8 hướng (như Vua cờ vua)
- Không được: ra ngoài bàn, vào ô chướng ngại vật, vào quân cùng phe
- **Bắt quân**: Chỉ khi quân đi **khắc chế** quân đối thủ
  - Búa thắng Kéo
  - Kéo thắng Bao
  - Bao thắng Búa
- Cùng loại: **chặn nhau** (không bắt được)

### 2.3 Điều kiện kết thúc (kiểm tra theo thứ tự sau mỗi nước)
1. **Thắng đến đích**: Quân vừa đi tới ô đích đối phương
2. **Thắng loại quân**: Bắt hết **một loại** quân đối thủ (ví dụ: hết 3 Kéo)
3. **Thắng do đối thủ hết nước**: Bên đến lượt không có nước hợp lệ
4. **Hòa lặp trạng thái**: Cùng trạng thái bàn (vị trí+loại+chủ sở hữu+tới lượt) xuất hiện **3 lần**
5. **Hòa giới hạn nước**: Chạm **300 ply** (mỗi ply = 1 nước của 1 bên)

### 2.4 Xử lý bot lỗi
Bot bị **thua ván (forfeit)** khi: timeout (>5s), crash, JSON sai, nước không trong `legal_moves`, vượt output (64 KiB), userdata >4 KiB.
Lỗi hạ tầng (Docker down, mất image) → **không tính điểm**, BTC chạy lại.

---

## 3. KIẾN TRÚC HỆ THỐNG

### 3.1 Sơ đồ module chính
```
Game-oan-tu-xi/
├── config/                 # Django settings, URLs, WSGI/ASGI
├── matches/                # Core game logic
│   ├── game_engine.py      # Engine luật chơi (độc lập framework)
│   ├── engine.py           # Engine web (port từ JS, 0-indexed)
│   ├── bot_runner.py       # Docker sandbox runner
│   ├── match_manager.py    # Điều phối trận đấu
│   ├── tournament.py       # Vòng tròn hai lượt: freeze/run/rank
│   ├── models.py           # Match, MatchMove
│   ├── views.py            # REST API
│   └── serializers.py
├── submissions/            # Nộp bài, duyệt, biên nhận
├── judge/                  # (Legacy) Judge0 client - không dùng trong K71
├── sandbox/                # Dockerfile cho image ott-bot:1
├── docs/                   # Tài liệu luật, chấm điểm, vận hành
└── bots/                   # Bot mẫu student1_bot.py, student2_bot.py
```

### 3.2 Luồng dữ liệu trận đấu
```
Web UI (tải 2 file .py)
    ↓ POST /api/matches/
Django View → MatchManager.run(p1_source, p2_source, preset)
    ↓
GameState (game_engine.py) — trạng thái bàn, legal_moves
    ↓
BotRunner (Docker container)
    ├─ docker create --memory=256m --cpus=1 --pids-limit=32 --network=none --read-only --user=65534
    ├─ docker start → docker exec python -I -B /bot.py
    ├─ Gửi JSON qua stdin (board, legal_moves, userdata)
    └─ Nhận JSON qua stdout (move + userdata)
    ↓
GameState.apply_move() → validate với legal_moves → cập nhật bàn
    ↓
Lưu events (started, move, finished) → trả về replay hoàn chỉnh
```

### 3.3 Game Engine (`matches/game_engine.py`) — **Nguồn chân lý duy nhất**
- **Không phụ thuộc Django**, có thể test độc lập
- Tọa độ công khai: **1-based** (row, col từ 1-9)
- Class chính: `GameState`
  - `legal_moves(player)` — sinh **tất cả** nước hợp lệ
  - `apply_move(proposed)` — xác thực + thực thi + trả event
  - `bot_input(match_id, userdata)` — build JSON cho bot
  - `snapshot()` — trạng thái đầy đủ để replay
  - `finish(winner, result, code, message)` — kết thúc trận
- Preset bàn: `classic_9x9`, `rectangle_7x11`, `cross_9x9`, `obstacles_9x9`
- Validation cấu hình: `validate_board_config()`

---

## 4. GIAO THỨC BOT (JSON QUA STDIN/STDOUT)

### 4.1 Input (Engine → Bot)
```json
{
  "protocol_version": "1.0",
  "match_id": "match-abc123",
  "turn": 1,
  "ply": 0,
  "current_player": "P1",
  "board": {
    "rows": 9, "cols": 9, "shape": "rectangle",
    "playable_cells": null,
    "blocked_cells": [],
    "goals": {"P1": [9,9], "P2": [1,1]}
  },
  "players": {
    "P1": {"goal": [9,9], "pieces": [{"id": "P1-S1", "type": "scissors", "at": [1,1]}, ...]},
    "P2": {"goal": [1,1], "pieces": [...]}
  },
  "legal_moves": [
    {"piece_id": "P1-S1", "from": [1,1], "to": [2,1], "capture_piece_id": null, "capture": false, "wins_immediately": false}
  ],
  "userdata": null
}
```

### 4.2 Output (Bot → Engine)
```json
{
  "move": {"piece_id": "P1-S1", "from": [1,1], "to": [2,1]},
  "userdata": {"custom": "state"}
}
```

### 4.3 Bot mẫu tối giản (`ai_sample.py`)
```python
import json, sys
state = json.load(sys.stdin)
if not state["legal_moves"]:
    print(json.dumps({"move": None}))
else:
    m = state["legal_moves"][0]
    print(json.dumps({"move": {"piece_id": m["piece_id"], "from": m["from"], "to": m["to"]}, "userdata": state.get("userdata")}))
```

---

## 5. HỆ THỐNG CHẠY BOT AN TOÀN (BOT_RUNNER.PY)

### 5.1 Nguyên tắc bảo mật
- **Không bao giờ chạy code upload trực tiếp trong process web**
- Mỗi lượt: tạo **container Docker mới** (`docker create ... --network=none --read-only --user=65534:65534`)
- Giới hạn: **256 MiB RAM**, **1 CPU**, **32 PIDs**, **8 MiB /tmp**, **5 giây wall-time**
- File bot mount **read-only** vào `/bot.py`
- Kill toàn bộ process group khi timeout (`docker kill`)

### 5.2 Xử lý lỗi phân loại
| Loại lỗi | Code | Xử lý |
|----------|------|-------|
| Bot crash/timeout/JSON sai | `BotError` | Thua ván (forfeit), ghi rõ lý do |
| Docker không chạy/image lỗi | `RunnerUnavailable` | **Lỗi hạ tầng** — không tính điểm, BTC chạy lại |

---

## 6. QUẢN LÝ TRẬN ĐẤU (MATCH_MANAGER.PY)

### 6.1 Chức năng
- Khởi tạo `GameState` từ preset
- Khởi tạo 2 `BotRunner` (P1, P2)
- Vòng lặp: kiểm tra hết nước → gọi bot → validate move → cập nhật state
- Xử lý forfeit khi bot lỗi
- Trả về object chứa: `id`, `events[]`, `state`, `bot_runs[]`, `reason`

### 6.2 Cấu trúc replay (events)
```json
{
  "type": "move",
  "ply": 5,
  "player": "P1",
  "piece_id": "P1-R1",
  "piece_type": "rock",
  "from": [1,2],
  "to": [2,3],
  "captured_piece": {"id": "P2-S1", "type": "scissors", "owner": "P2", "at": [2,3]},
  "message": "P1: rock [1,2] → [2,3]",
  "state_after": { ... }
}
```

---

## 7. HỆ THỐNG GIẢI THI ĐẤU (TOURNAMENT.PY)

### 7.1 Ba lệnh chính
```bash
# 1. Khóa bài (freeze) — chạy 1 lần trước giải
python -m matches.tournament freeze entries.json tournament_dir --image sha256:abc123

# 2. Chạy giải (run) — có thể resume sau sự cố
python -m matches.tournament run tournament_dir

# 3. Xuất xếp hạng (rank)
python -m matches.tournament rank tournament_dir --output ranking.json [--provisional]
```

### 7.2 Manifest (khóa bất biến)
- `engine_sha256`: hash của 4 file engine/core
- `image`: Docker image ID (`sha256:...`) đã build và test
- `teams[]`: team_id, name, **sha256 file .py**
- `schedule[]`: vòng tròn hai lượt (N đội → N×(N-1) ván)

### 7.3 Tính năng vận hành
- **Resume**: Bỏ qua ván đã có file kết quả trong `results/`
- **Atomic write**: Ghi file `.tmp` → `os.replace()` tránh file hỏng
- **Lock file**: `.running` tránh 2 process chạy cùng lúc
- **Lỗi hạ tầng**: Dừng ngay, ghi vào `attempts/`, không tính điểm

### 7.4 Xếp hạng (theo CHAM_DIEM_XEP_HANG.md)
| Tiêu chí | Thứ tự |
|----------|--------|
| 1. Tổng điểm (Thắng=3, Hòa=1, Thua=0) | Giảm dần |
| 2. Đối đầu trong nhóm đồng điểm | Giảm dần |
| 3. Sonneborn-Berger (SB) | Giảm dần |
| 4. Số ván thắng | Giảm dần |
| 5. Còn hòa → **Đồng hạng** (hiển thị 1, 2, 2, 4) | — |

---

## 8. WEB API (DJANGO REST FRAMEWORK)

### 8.1 API Trận đấu (`matches/views.py`)
| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/api/matches/` | POST | Tạo trận mới (upload 2 file bot) |
| `/api/matches/` | GET | Danh sách trận của user |
| `/api/matches/{id}/` | GET | Chi tiết trận + replay |
| `/api/matches/{id}/ai-move/` | POST | Yêu cầu AI đi 1 nước (dùng Judge0 - legacy) |
| `/api/matches/ai-battle/start/` | POST | Chạy ngay AI vs AI (sync) |
| `/api/matches/{id}/battle/` | GET | Trạng thái + toàn bộ nước đi |

### 8.2 API Nộp bài (`submissions/views.py`)
- Upload file `.py` (max 64 KiB, UTF-8)
- Tự động kiểm tra syntax (`ast.parse`)
- Tính SHA-256, trả biên nhận
- Admin duyệt (`review_status = approved`) → mới được dùng thi đấu

### 8.3 Giao diện Web (Demo)
- Trang chủ `/` — hướng dẫn
- `/ai/` — Nộp bài, xem biên nhận
- `/battlecode/` — Chọn 2 bot mẫu, chọn preset, chạy demo, xem replay
- `/history/` — Lịch sử trận đã chơi
- `/admin/code-review/` — Admin duyệt bài

**Replay Viewer**: Play/Pause, Step (1 nước), Speed (0.25x–2x), nhảy theo lịch sử nước đi.

---

## 9. TÍNH NĂNG NỔI BẬT KỸ THUẬT

### 9.1 Tách biệt Engine và Web
- `game_engine.py` **không import Django** → test độc lập, dùng cho tournament CLI
- Web engine (`engine.py`) dùng 0-indexed internal, chuyển đổi khi giao tiếp

### 9.2 Xác thực nước đi chặt chẽ
- Engine sinh `legal_moves` → bot **chỉ được chọn** trong danh sách này
- `apply_move()` so khớp `piece_id`, `from`, `to` chính xác
- Không tin tưởng output bot tự khai

### 9.3 Replay có thể tái lập (Deterministic)
- Cùng bot, cùng preset, cùng seed → cùng replay
- Lưu `state_after` mỗi nước → nhảy tới bất kỳ trạng thái nào
- Hash replay (`replay_sha256`) trong manifest đảm bảo không bị sửa

### 9.4 Hỗ trợ nhiều hình bàn (Extensible)
Cấu hình dữ liệu (data-driven):
```json
{
  "rows": 9, "cols": 9,
  "playable_cells": [[1,4],...],  // null = toàn bàn
  "blocked_cells": [[5,5]],
  "goals": {"P1": [9,9], "P2": [1,1]},
  "initial_pieces": [...]
}
```
4 preset sẵn: classic, rectangle, cross, obstacles.

### 9.5 Không phụ thuộc Judge0 (phiên bản K71)
- Demo web dùng bot mẫu chạy trực tiếp (không sandbox) để minh họa nhanh
- Giải chính thức: chỉ dùng `matches.tournament` + Docker worker riêng
- Code cũ Judge0/AI Judge/ELO/room 8 người đã được loại bỏ theo SYSTEM_SPEC.md

---

## 10. QUY TRÌNH TRIỂN KHAI GIẢI CHÍNH THỨC

### 10.1 Chuẩn bị (trước giải)
1. Build Docker image: `docker build -t ott-bot:1 sandbox/`
2. Lấy image ID: `docker image inspect ott-bot:1 --format "{{.Id}}"` → `sha256:...`
3. BTC chuẩn bị `entries.json`:
```json
[
  {"team_id": "TEAM01", "name": "Đội A", "path": "bots/TEAM01.py"},
  {"team_id": "TEAM02", "name": "Đội B", "path": "bots/TEAM02.py"}
]
```

### 10.2 Khóa bài (Freeze)
```bash
python -m matches.tournament freeze entries.json tournament_k71 --image sha256:abc123
```
→ Tạo thư mục `tournament_k71/` chứa: `manifest.json`, `bots/*.py`, `results/`, `attempts/`
→ **Sao lưu toàn bộ thư mục này** (offsite) trước khi chạy.

### 10.3 Chạy giải (Run)
```bash
python -m matches.tournament run tournament_k71
```
- Chạy tuần tự, in log từng ván
- Nếu lỗi hạ tầng → dừng, sửa lỗi, chạy lại (resume tự động)

### 10.4 Xuất kết quả (Rank)
```bash
python -m matches.tournament rank tournament_k71 --output ranking_k71.json
```
→ File JSON chứa bảng xếp hạng đầy đủ (rank, points, SB, wins, draws, losses)

---

## 11. KIỂM THỬ VÀ ĐẢM BẢO CHẤT LƯỢNG

### 11.1 Unit Test Engine (`matches/tests.py`, `test_tournament_core.py`)
- Di chuyển 8 hướng, chặn ra ngoài bàn, chặn quân cùng phe
- Khắc chế: Búa>Kéo, Kéo>Bao, Bao>Búa
- Thắng: đến đích, loại loại quân, hết nước
- Hòa: lặp 3 lần, 300 ply
- Bàn chữ nhật, chữ thập, chướng ngại vật
- Validation cấu hình sai (quân trùng, đích trên obstacle...)

### 11.2 Test Runner/Giao thức
- Bot Python hợp lệ / C++ hợp lệ (nếu mở rộng)
- Xử lý: JSON sai, nước không hợp lệ, crash, timeout, output lớn
- Engine không gọi bot khi `legal_moves` rỗng

### 11.3 Test UI
- Upload 2 file → tạo trận → xem bàn + lịch sử
- Play/Pause/Step/Replay + đổi tốc độ
- Hiển thị đúng lượt, quân bắt, kết quả
- Responsive trên màn hình nhỏ

### 11.4 Chạy test
```bash
# Engine + Tournament core
python -m unittest matches.test_tournament_core

# Django tests (in-memory SQLite)
.venv/Scripts/python manage.py test matches.tests matches.tests_battlecode matches.tests_security submissions.tests_receipts submissions.tests --settings=config.test_settings
```

---

## 12. VẤN ĐỀ THƯỜNG GẶP VÀ GIẢI PHÁP (CHO PHÒNG VẤN)

| Câu hỏi thường gặp | Trả lời ngắn gọn |
|-------------------|------------------|
| **Tại sao dùng Docker không dùng Judge0?** | Judge0 là dịch vụ ngoài, phức tạp, khó kiểm soát resource. Docker local cho隔离 hoàn toàn, không network, giới hạn CPU/RAM/PIDs chính xác, phù hợp chạy offline trên máy chấm của trường. |
| **Bot có thể làm hỏng server không?** | Không. Bot chạy trong container `--read-only --network=none --user=65534 --cap-drop=ALL --security-opt=no-new-privileges`. Web process chỉ gọi `docker create/start/exec/rm`. |
| **Làm sao đảm bảo công bằng?** | Cùng image Docker, cùng giới hạn, cùng engine version (hash trong manifest). Bot không thấy nhau, không chia sẻ state. Khóa bài SHA-256 trước giải. |
| **Tại sao không dùng database cho tournament?** | Tournament CLI dùng file JSON atomic write — đơn giản, không cần DB server, dễ backup/scp, phù hợp máy chấm offline. Web dùng Django ORM cho tài khoản/bài nộp. |
| **Có hỗ trợ C++ không?** | Engine/giao thức hỗ trợ (bot_runner kiểm tra suffix), nhưng thể lệ K71 chỉ cho Python. Code sẵn sàng mở rộng nếu cần. |
| **Làm sao xử lý bot timeout?** | `docker exec` có timeout 5s (wall-time). Quá hạn → `docker kill` container → raise `BotError('timeout')` → thua ván. |
| **Replay có bị chỉnh sửa không?** | Không. Mỗi ván có `replay_sha256` trong file kết quả. Manifest hash toàn bộ engine + image. Thay đổi bất kỳ file nào → `load_frozen()` báo lỗi. |
| **Nếu máy chấm chết giữa chừng?** | Lock file `.running` + atomic write. Chạy lại `run tournament_dir` → tự động skip ván đã xong (có file trong `results/`). |
| **Tại sao có 2 engine (game_engine.py và engine.py)?** | `game_engine.py` = core logic (1-based, tournament CLI, không Django). `engine.py` = port từ JS cũ (0-indexed), dùng cho web demo/AI battle legacy. Chúng dùng cùng logic luật. |

---

## 13. CÁC FILE QUAN TRỌNG CẦN BIẾT (CHO PHÒNG VẤN CODE)

| File | Vai trò | Điểm quan trọng |
|------|---------|-----------------|
| `matches/game_engine.py` | **Core engine** | `GameState`, `legal_moves`, `apply_move`, `bot_input`, `validate_board_config` |
| `matches/bot_runner.py` | **Sandbox** | `BotRunner.run_turn()` — Docker create/exec/kill, resource limits |
| `matches/match_manager.py` | **Orchestrator** | `MatchManager.run()` — vòng lặp trận đấu, xử lý forfeit/infra error |
| `matches/tournament.py` | **Giải đấu** | `freeze/run/rank`, `standings()` với tiebreakers, manifest locking |
| `matches/engine.py` | **Web engine** | `GameState` (0-indexed), `build_ai_input`, `parse_ai_output`, `validate_ai_move` |
| `matches/views.py` | **Web API** | `MatchListCreateView`, `ai_battle_start_view`, `ai_battle_status_view` |
| `submissions/models.py` | **Bài nộp** | `Submission` với `sha256`, `review_status`, `ai_name`, `version` |
| `docs/LUAT_THI_DAU_K71.md` | **Luật giải** | Thể lệ đầy đủ: bàn cờ, di chuyển, thắng/thua, giao thức, tài nguyên, nộp bài, khiếu nại |
| `docs/CHAM_DIEM_XEP_HANG.md` | **Chấm điểm** | 3-1-0, vòng tròn, SB, đối đầu, đồng hạng, vòng phụ |
| `docs/HUONG_DAN_CHAY_GIAI.md` | **Vận hành** | Freeze, run, resume, rank, backup, khôi phục sự cố |

---

## 14. CHECKLIST TIÊU CHUẨN NGHIỆM THU (TỪ SYSTEM_SPEC.MD)

- [x] Người dùng mở web → thấy màn hình tạo trận
- [x] Upload 2 bot Python mẫu → chọn preset classic 9×9
- [x] Nhấn bắt đầu → hệ thống tự điều khiển 2 bên đến khi có kết quả
- [x] Bàn cờ cập nhật theo từng nước, mặc định 1 giây/nước
- [x] Có Play/Pause/Step/Replay, đổi tốc độ
- [x] Lịch sử nước đi khớp hoàn toàn state trên bàn
- [x] Bot sai giao thức/timeout/đi sai → thua ván rõ lý do, không sập server
- [x] Ít nhất 1 preset chữ thập + 1 preset obstacle hoạt động ở engine
- [x] Không còn phụ thuộc Judge0, không còn AI Judge/ELO/multiplayer trong demo
- [x] README hướng dẫn cài đặt/chạy + giao thức bot + 2 file mẫu

---

## 15. HƯỚNG DẪN CHẠY LOCAL (DEMO NHANH)

```powershell
# 1. Clone & cài đặt
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py createsuperuser  # tài khoản admin
.venv/Scripts/python manage.py runserver

# 2. Mở trình duyệt: http://127.0.0.1:8000/
# - /battlecode/ : chọn 2 bot mẫu (student1_bot.py, student2_bot.py) → Chạy demo
# - /ai/ : nộp file .py của bạn (tự test trước bằng: python your_bot.py < bots/sample_input.json)

# 3. Test giao thức bot mẫu
python bots/student1_bot.py < bots/sample_input.json
python bots/student2_bot.py < bots/sample_input.json
# Phải in 1 dòng JSON có move.piece_id, from, to
```

---

## 16. TỔNG KẾT ĐIỂM MẠNH CỦA DỰ ÁN

1. **Tách biệt rõ ràng**: Engine luật chơi hoàn toàn độc lập với web framework → dễ test, dễ review, dùng cho cả CLI tournament.
2. **Bảo mật mạnh**: Docker sandbox với đầy đủ giới hạn (CPU, RAM, PIDs, network, filesystem, user) — code sinh viên không bao giờ chạm host.
3. **Tái lập được**: Manifest khóa hash engine + image + bài thi → mọi ván đều có thể chạy lại chính xác.
4. **Chuẩn hóa thi đấu**: Vòng tròn hai lượt, chấm điểm 3-1-0, tiebreaker SB/đối đầu, hỗ trợ 2-128 đội, resume sau sự cố.
5. **Tuân thủ thể lệ K71**: Luật chơi, giao thức bot, giới hạn tài nguyên, quy trình khóa bài/chạy giải/xuất hạng đều có tài liệu chi tiết.
6. **Code sạch, có test**: Unit test cho engine, runner, tournament core; Django test in-memory SQLite.

---

## 17. LIÊN HỆ / THAM KHẢO

- **Repository**: Local tại `C:\Users\Admin\.vscode\Game-oan-tu-xi`
- **Tài liệu luật**: `docs/LUAT_THI_DAU_K71.md`
- **Tài liệu chấm điểm**: `docs/CHAM_DIEM_XEP_HANG.md`
- **Hướng dẫn chạy giải**: `docs/HUONG_DAN_CHAY_GIAI.md`
- **Đặc tả hệ thống**: `SYSTEM_SPEC.md`
- **README**: `README.md`

---

*Tài liệu này được tổng hợp từ source code và các file docs trong dự án. Dùng cho mục đích bảo vệ đồ án môn học / giải thi đấu K71.*