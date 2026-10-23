# HƯỚNG DẪN CHẠY GIẢI LOCAL V1

Thể lệ: [Luật K71](LUAT_THI_DAU_K71.md). Chấm điểm: [3–1–0 và phá hòa](CHAM_DIEM_XEP_HANG.md).

## 1. Demo website

Chạy Django như hướng dẫn dự án. Trang `/battlecode/` cho xem hai chiến thuật mẫu. Các API upload-and-run cũ trả thông báo không chạy code trên web. Trang nộp AI vẫn nhận mã, kiểm tra cú pháp, giới hạn kích thước, lưu phiên bản và trả SHA-256.

Demo không đòi Docker. Demo không cộng điểm giải, không gắn trận mẫu vào mùa giải đang hoạt động. Lịch sử chỉ chủ tài khoản hoặc admin xem được qua API replay.

## 2. Chuẩn bị máy chấm

Dùng Linux hoặc Docker Desktop ở chế độ Linux containers để diễn tập. Giải thật dùng máy/VM chuyên dụng không có secret web và dữ liệu cá nhân. Python trên host chỉ điều phối, không thực thi file nộp. Không có cơ chế tự fallback sang chạy Python trên host nếu Docker hỏng.

Tại thư mục dự án:

```text
docker build -t ott-bot:1 sandbox
docker image inspect ott-bot:1 --format "{{.Id}}"
```

Lưu image ID dạng `sha256:...`. Build cần Internet; chạy giải dùng image có sẵn (`--pull=never`). Cất bản image cùng release để có thể phục hồi. Dockerfile dùng Python 3.12; mỗi lần build có thể lấy bản vá mới, vì vậy chỉ khóa image sau diễn tập, không rebuild giữa giải.

Mỗi nước có container mới chỉ mount **một file bot** read-only, không mạng, non-root, cap-drop, no-new-privileges, hạn CPU/RAM/PID/file/output. Việc tạo container mỗi nước ưu tiên đơn giản và sạch trạng thái, có overhead; phải đo trước khi tính lịch giải. `userdata` là cơ chế giữ bộ nhớ duy nhất được hỗ trợ.

## 3. Xuất bài từ web và chọn đội

Nếu dùng đăng ký cá nhân/đội trên web, BTC khóa thành viên và mục dự thi trước khi chọn bài:

```text
python manage.py lock_season_entries <season_id>
```

Lệnh khóa mã đội và chặn nộp thêm cho mục dự thi. Sau đó BTC đối chiếu đội trưởng, thành viên, phiên bản bài và SHA-256 theo biên bản. Không chạy lệnh này trước khi kết thúc thời gian đổi đội.

BTC xác nhận mã bài của từng đội. Có thể tải source bằng tài khoản admin rồi lưu UTF-8, đối chiếu SHA-256 trả trong API; không copy qua công cụ làm thay đổi newline/encoding. Với dữ liệu Django local, dùng management command:

```text
python manage.py export_competition_entries selections.json private-exports/k71
```

`selections.json` có dạng:

```json
[
  {"team_id":"K71_001","name":"Đội 1","submission_id":1},
  {"team_id":"K71_002","name":"Đội 2","submission_id":2}
]
```

Lệnh chỉ xuất bài đã duyệt, khóa giao dịch khi đọc, đánh dấu bài đã sử dụng để ngăn thao tác xóa qua API và ghi biên nhận. Không tự quyết định đội nào hợp lệ hoặc bài nào được chọn trước deadline. BTC phải kiểm tra deadline/danh sách thành viên theo biên bản.

Không cần Django nếu đã có file local. Tạo `entries.json`, đường dẫn file tính từ nơi đặt `entries.json`:

```json
[
  {"team_id":"K71_001","name":"Đội 1","path":"team1.py"},
  {"team_id":"K71_002","name":"Đội 2","path":"team2.py"}
]
```

## 4. Khóa bài, chạy và tiếp tục

Thay `<IMAGE_ID>` bằng giá trị thực ở bước 2; không giữ nguyên dấu `< >`.

```text
python -m matches.tournament freeze private-exports/k71/entries.json tournament-data/k71 --image <IMAGE_ID>
python -m matches.tournament run tournament-data/k71
```

Lệnh freeze tạo thư mục mới, sao chép bài, kiểm tra cú pháp sơ bộ, hash bài và mã điều phối, cố định 300 nước/5 giây, lưu image ID và lịch hai lượt. Cú pháp trên host chưa thay thế chạy kiểm tra bằng đúng Python 3.12. Chỉ đưa bài đã qua kiểm tra vào giải thật.

Sau khi khóa, sao lưu toàn bộ thư mục và release code ra thiết bị/kho lưu khác do BTC quản lý; ghi hash `manifest.json` vào biên bản độc lập. Hash lưu cạnh file chỉ phát hiện sửa nhầm, không ngăn người có quyền sửa cả file và hash. Không cho sinh viên quyền sửa thư mục giải.

Nếu lỗi hạ tầng, công cụ giữ lần lỗi trong `attempts/`, dừng để BTC xử lý. Chạy lại cùng lệnh `run` sẽ bỏ qua ván đã có kết quả hợp lệ, chạy lại ván chưa hoàn tất. Không tự cộng điểm lần hai.

File `.running` ngăn hai tiến trình chấm cùng thư mục. Nếu máy bị tắt đột ngột, BTC xác minh không còn tiến trình điều phối/container cũ, ghi nhận sự cố rồi xóa riêng file `.running` trước khi tiếp tục. Không xóa cả thư mục. Container có tên `ott-...`; kiểm tra container tồn dư khi khôi phục máy chấm.

Nếu source, engine hoặc image khai báo bị thay đổi, công cụ từ chối tiếp tục. Khôi phục bản đúng từ backup; thay đổi luật phải mở phiên bản/giải mới theo quyết định BTC.

## 5. Xuất bảng xếp hạng

```text
python -m matches.tournament rank tournament-data/k71 --provisional --output private-exports/ranking-tam.json
python -m matches.tournament rank tournament-data/k71 --output private-exports/ranking-cuoi.json
```

Lệnh không có `--provisional` sẽ từ chối khi còn ván chưa có kết quả. File xuất phải nằm ngoài thư mục giải và có tên chưa tồn tại. Công cụ xuất thứ hạng, điểm, thắng/hòa/thua, đối đầu, SB và số ván còn thiếu; không công bố lên web hay Google Sheets.

BTC chỉ đăng file/bảng vào thời gian công bố đã định. Giữ file đầy đủ trong kho riêng, chỉ chia sẻ dữ liệu cần thiết. Replay có stderr có thể chứa thông tin do bot ghi; cần lọc trước khi công khai.

Mỗi bảng thi là một thư mục độc lập. Chung kết/vòng phụ dùng thư mục mới, cùng bản bot đã khóa. Công cụ không tự quyết định suất đi tiếp, kỷ luật hay bốc thăm.

## 6. Kiểm tra mã nguồn

```text
python -m unittest matches.test_tournament_core
python manage.py test matches.tests matches.tests_battlecode matches.tests_security submissions.tests_receipts --settings=config.test_settings
python manage.py check --settings=config.test_settings
```

Unit test runner dùng giả lập để kiểm tra phân loại lỗi và cấu hình; không thay thế thử sandbox thật. Phải bổ sung diễn tập Docker, tải web và restore trên môi trường nhà trường trước khi mở giải chính thức.
