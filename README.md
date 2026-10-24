Link: https://13.211.201.112
# Oẳn Tù Tì 2.0 — Demo và công cụ giải K71

Sinh viên viết Python điều khiển quân trên bàn 9 × 9. Thắng khi đến đích hoặc bắt hết **một loại quân** của đối phương. Engine cũng xử lý hết nước đi, hòa lặp trạng thái và giới hạn 300 nước.

## Tài liệu trình thầy và nhà trường

- [Luật thi đấu chi tiết](docs/LUAT_THI_DAU_K71.md): bàn cờ, bố trí, di chuyển, thắng/hòa/thua, giao thức, giới hạn, nộp bài.
- [Chấm điểm và xếp hạng](docs/CHAM_DIEM_XEP_HANG.md): 3–1–0, đổi bên, vòng bảng/chung kết, đối đầu, SB và đồng hạng.
- [Luật, bốc thăm và sơ đồ giải](docs/LUAT_XEP_BANG_VA_SO_DO_GIAI.md): chia bảng, demo World Cup 48 đội và nhánh tới chung kết.
- [Host demo và phương án tiết kiệm](docs/HOST_DEMO_VA_VAN_HANH.md): giữ Render demo, lựa chọn sau khi cấp kinh phí, chi phí tham chiếu và vận hành.
- [Hướng dẫn chạy giải local](docs/HUONG_DAN_CHAY_GIAI.md): xuất bài, khóa hash, chạy Docker, tiếp tục sau sự cố và xuất kết quả.

Các điều lệ là bản đề xuất k71-v1.0 để trường phê duyệt trước giải; code hiện theo cấu hình này. `SYSTEM_SPEC.md` và `SETUP.md` chứa thiết kế lịch sử, không dùng làm luật giải hiện tại.

## Phạm vi hiện có

| Thành phần | Hành vi |
|---|---|
| Django web | Đăng nhập, một tài khoản đại diện đăng ký mùa giải, bốc thăm/bảng đấu, nộp code, duyệt và biên nhận |
| `/battlecode/` | Hai chiến thuật mẫu tin cậy, replay lưu DB, không cộng điểm giải |
| File Python tải lên | Chỉ lưu bài; không chạy trực tiếp trong HTTP request |
| Công cụ local | Khóa bài, vòng tròn hai lượt, Docker runner, lưu từng ván, resume, xếp hạng |
| ELO/phòng chơi người | Tính năng luyện tập cũ; không dùng làm kết quả giải K71 |

Engine chính thức: `matches/game_engine.py`. Giao thức dùng `piece_id`, `from`, `to`, tọa độ từ **1**. Các luồng người chơi cũ có mô hình nội bộ khác; không dùng giao thức Judge0 cũ làm mẫu bài thi.

## Mô hình tham gia hiện tại

Mỗi nhóm cử một sinh viên dùng một tài khoản đại diện để đăng ký, nộp và chọn bot. Web không quản lý thành viên, mã mời, email hoặc khiếu nại. Admin chỉ dùng các mục Mùa giải, Bài nộp, Chấm bài, Lịch sử đấu và Hướng dẫn. Luồng mùa: Đăng ký → Nộp bài → Khóa bài → Thi đấu → Kết thúc.

## Chạy web local

Tổ chức giải tối đa 4.000 người, 4 máy chấm Docker và thanh tiến độ: xem [hướng dẫn vận hành](docs/TO_CHUC_GIAI_4_MAY_CHAM.md). Trang mới `/tournament/` quản lý giai đoạn, phiên bản bot, hàng đợi, tiến độ, replay, thông báo.

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

Sau mỗi lần `git pull`, cập nhật cấu trúc database trước khi chạy lại server:

```powershell
venv/Scripts/python manage.py migrate
venv/Scripts/python manage.py runserver
```

Nếu dùng môi trường `.venv` thì thay `venv/` bằng `.venv/`. Truy cập http://localhost:8000/ (cần có cổng `8000`). Lỗi `no such column` hoặc `no such table` thường do chưa chạy migration mới. Database và cache Python được giữ riêng trên từng máy, không đưa vào Git.

## Bot mẫu

`ai_sample.py` là ví dụ tối giản; `bots/student1_bot.py` và `bots/student2_bot.py` là chiến thuật tham khảo. Bot đọc một JSON từ stdin, trả một JSON rồi thoát:

```python
import json, sys
state = json.load(sys.stdin)
move = state['legal_moves'][0]
print(json.dumps({'move': {k: move[k] for k in ('piece_id', 'from', 'to')}}))
```

Nếu không còn nước hợp lệ, engine xử lý trước khi gọi bot. `userdata` tùy chọn giúp giữ trạng thái giữa các lần gọi; không dựa vào file từ lượt trước.

## Luyện tập với bot đã nộp

Sinh viên mở `/practice/`, chọn phiên bản của mình, bot mẫu hoặc bot đã được duyệt làm đối thủ và bên P1/P2. Trận dùng source snapshot, được bộ chấm local trên server chạy qua sandbox hiện có của nhánh: ưu tiên Isolate khi khả dụng, Docker dự phòng. Không chạy trực tiếp code học sinh trên host và không cộng điểm mùa/Elo. Lịch sử/replay chỉ dành cho chủ trận; stderr của đối thủ được ẩn.

Mặc định 10 trận/ngày, một trận queued/running mỗi tài khoản, có thể hủy queued. Bộ chấm ưu tiên job chính thức sẵn sàng trước job luyện tập; trận đang chạy được hoàn tất. Khi `LOCAL_JUDGE_AUTOSTART=True`, tạo trận sẽ tự khởi động bộ chấm sau khi lưu thành công, không cần token worker riêng. Có thể dùng `python manage.py run_judge --watch` nếu muốn chạy bộ chấm bằng lệnh. Cần chạy `python manage.py migrate` khi cập nhật web; migration merge giữ cả đặc tả đề bài và lịch sử luyện tập.

`PRACTICE_MATCHES_PER_DAY` chỉnh hạn mức; `PRACTICE_DOCKER_IMAGE` để trống sẽ dùng `TOURNAMENT_DOCKER_IMAGE` (mặc định `ott-bot:1`). Không cần nhập mã image SHA-256 trên admin. Sandbox vẫn cần khả dụng trên máy server; cơ chế tự nhận Isolate/tạo image Docker của nhánh được giữ nguyên.

## Chạy giải

```text
docker build -t ott-bot:1 sandbox
docker image inspect ott-bot:1 --format "{{.Id}}"
python -m matches.tournament --help
```

Làm theo [hướng dẫn đầy đủ](docs/HUONG_DAN_CHAY_GIAI.md). Không mount Docker socket vào web. Runner chỉ hoạt động khi có Docker; không có fallback chạy bot trực tiếp trên host. Mã nguồn, manifest và replay thật nằm trong `private-exports/` và `tournament-data/`, đã loại khỏi Git.

## Nộp bài khi mất mạng

**Tổ chức ngay trong lớp không cần Internet:** xem [hướng dẫn chạy LAN](docs/CHAY_GIAI_TRONG_LAN.md).
Chạy `python run_classroom.py --address <IPv4 máy giáo viên>` để mở web và bộ chấm
trên một máy. Sinh viên nộp qua LAN; mất cả LAN thì lưu bài chờ trên trình duyệt.
HTTP LAN phải giữ tab nộp bài mở khi mất LAN; mở lại trang offline cần HTTPS.

Mở trang `/ai/` online và đăng nhập trước một lần. Khi hiện “Đã sẵn sàng mở trang Nộp AI offline”, có thể mở lại trang này khi mất mạng. Cần HTTPS khi triển khai, localhost dùng được khi phát triển.

Trang tự lưu bản nháp bằng IndexedDB. Bấm **Nộp bài** để lưu một bản cố định vào hàng đợi trên trình duyệt; giữ/mở lại trang khi có mạng để tự gửi. Chỉ thông báo **Server đã nhận** kèm biên nhận mới xác nhận nộp thành công. Hết phiên phải đăng nhập đúng tài khoản; bài quá hạn vẫn bị server từ chối. Có nút tải `.py` dự phòng, gửi lại và xóa dữ liệu máy chung. Không bảo đảm gửi nền khi đã đóng trình duyệt.

Server dùng `client_submission_id` UUID và biên nhận theo tài khoản để gửi lại không tạo phiên bản hoặc trừ quota hai lần. Cần chạy `python manage.py migrate` sau cập nhật. Không cache trang cá nhân/API; Service Worker chỉ cache shell ẩn danh và static. Queue này khác queue chấm trên máy chủ.

## Kiểm tra

```text
python -m unittest matches.test_tournament_core
.venv/Scripts/python manage.py test matches.tests matches.tests_battlecode matches.tests_security submissions.tests_receipts submissions.tests --settings=config.test_settings
.venv/Scripts/python manage.py check --settings=config.test_settings
```

Test Django dùng SQLite trong bộ nhớ, không ghi vào `db.sqlite3` đang có. Xem [biên bản kiểm tra](docs/KIEM_TRA_VA_GIOI_HAN.md) để biết phần đã kiểm tra và phần cần diễn tập thật trước giải.

## Host

Giữ Render cho demo. Chỉ nâng gói/thuê máy khi trường duyệt; ưu tiên web nhỏ trả phí cùng máy chấm của trường. Chưa triển khai AWS/Cloudflare và chưa phát sinh tài nguyên cloud trong thay đổi này. Render Free không phù hợp lưu bài thi chính thức lâu dài hoặc làm cam kết sẵn sàng.
