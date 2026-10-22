# Oẳn Tù Tì 2.0 — Demo và công cụ giải K71

Sinh viên viết Python điều khiển quân trên bàn 9 × 9. Thắng khi đến đích hoặc bắt hết **một loại quân** của đối phương. Engine cũng xử lý hết nước đi, hòa lặp trạng thái và giới hạn 300 nước.

## Tài liệu trình thầy và nhà trường

- [Luật thi đấu chi tiết](docs/LUAT_THI_DAU_K71.md): bàn cờ, bố trí, di chuyển, thắng/hòa/thua, giao thức, giới hạn, nộp bài và khiếu nại.
- [Chấm điểm và xếp hạng](docs/CHAM_DIEM_XEP_HANG.md): 3–1–0, đổi bên, vòng bảng/chung kết, đối đầu, SB và đồng hạng.
- [Host demo và phương án tiết kiệm](docs/HOST_DEMO_VA_VAN_HANH.md): giữ Render demo, lựa chọn sau khi cấp kinh phí, chi phí tham chiếu và vận hành.
- [Hướng dẫn chạy giải local](docs/HUONG_DAN_CHAY_GIAI.md): xuất bài, khóa hash, chạy Docker, tiếp tục sau sự cố và xuất kết quả.

Các điều lệ là bản đề xuất k71-v1.0 để trường phê duyệt trước giải; code hiện theo cấu hình này. `SYSTEM_SPEC.md` và `SETUP.md` chứa thiết kế lịch sử, không dùng làm luật giải hiện tại.

## Phạm vi hiện có

| Thành phần | Hành vi |
|---|---|
| Django web | Đăng nhập, nộp code, duyệt, biên nhận và hash bài |
| `/battlecode/` | Hai chiến thuật mẫu tin cậy, replay lưu DB, không cộng điểm giải |
| File Python tải lên | Chỉ lưu bài; không chạy trực tiếp trong HTTP request |
| Công cụ local | Khóa bài, vòng tròn hai lượt, Docker runner, lưu từng ván, resume, xếp hạng |
| ELO/phòng chơi người | Tính năng luyện tập cũ; không dùng làm kết quả giải K71 |

Engine chính thức: `matches/game_engine.py`. Giao thức dùng `piece_id`, `from`, `to`, tọa độ từ **1**. Các luồng người chơi cũ có mô hình nội bộ khác; không dùng giao thức Judge0 cũ làm mẫu bài thi.

## Chạy web local

Python có thể cài được các phiên bản trong `requirements.txt`. Bản kiểm tra local dùng Python 3.14; bot được quy định Python 3.12 trong container riêng.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py createsuperuser
.venv/Scripts/python manage.py runserver
```

Đặt `DJANGO_SECRET_KEY` riêng trong `.env`. Local dùng SQLite; Render dùng `DATABASE_URL`. Production yêu cầu secret riêng và `DJANGO_DEBUG=False`; cấu hình DB sai sẽ báo lỗi, không âm thầm chuyển sang SQLite.

Trang chính `/`, nộp bài `/ai/`, xem bot mẫu `/battlecode/`, lịch sử `/history/`, quản trị bài `/admin/code-review/`. Các API replay chỉ cho chủ trận hoặc admin xem. Demo không cần Docker hoặc Judge0.

## Bot mẫu

`ai_sample.py` là ví dụ tối giản; `bots/student1_bot.py` và `bots/student2_bot.py` là chiến thuật tham khảo. Bot đọc một JSON từ stdin, trả một JSON rồi thoát:

```python
import json, sys
state = json.load(sys.stdin)
move = state['legal_moves'][0]
print(json.dumps({'move': {k: move[k] for k in ('piece_id', 'from', 'to')}}))
```

Nếu không còn nước hợp lệ, engine xử lý trước khi gọi bot. `userdata` tùy chọn giúp giữ trạng thái giữa các lần gọi; không dựa vào file từ lượt trước.

## Chạy giải

```text
docker build -t ott-bot:1 sandbox
docker image inspect ott-bot:1 --format "{{.Id}}"
python -m matches.tournament --help
```

Làm theo [hướng dẫn đầy đủ](docs/HUONG_DAN_CHAY_GIAI.md). Không mount Docker socket vào web. Runner chỉ hoạt động khi có Docker; không có fallback chạy bot trực tiếp trên host. Mã nguồn, manifest và replay thật nằm trong `private-exports/` và `tournament-data/`, đã loại khỏi Git.

## Kiểm tra

```text
python -m unittest matches.test_tournament_core
.venv/Scripts/python manage.py test matches.tests matches.tests_battlecode matches.tests_security submissions.tests_receipts submissions.tests --settings=config.test_settings
.venv/Scripts/python manage.py check --settings=config.test_settings
```

Test Django dùng SQLite trong bộ nhớ, không ghi vào `db.sqlite3` đang có. Xem [biên bản kiểm tra](docs/KIEM_TRA_VA_GIOI_HAN.md) để biết phần đã kiểm tra và phần cần diễn tập thật trước giải.

## Host

Giữ Render cho demo. Chỉ nâng gói/thuê máy khi trường duyệt; ưu tiên web nhỏ trả phí cùng máy chấm của trường. Chưa triển khai AWS/Cloudflare và chưa phát sinh tài nguyên cloud trong thay đổi này. Render Free không phù hợp lưu bài thi chính thức lâu dài hoặc làm cam kết sẵn sàng.
