# Vận hành giải với tài khoản đại diện và 4 máy chấm

## Mô hình sử dụng

Mỗi nhóm cử một sinh viên dùng một tài khoản đại diện để đăng ký và nộp bot. Mỗi tài khoản có một mục dự thi trong mỗi mùa, có thể đặt tên hiển thị theo tên nhóm. Web không còn luồng lập/vào đội, mã mời, email hoặc khiếu nại. Thông báo được đăng trực tiếp trên web.

Giới hạn 4.000 tính số tài khoản đại diện (số mục dự thi), không đếm thành viên làm nhóm ngoài web. Đây không phải chứng nhận 4.000 truy cập đồng thời.

Menu admin gồm Mùa giải, Bài nộp, Chấm bài, Lịch sử đấu và Hướng dẫn. Tài khoản staff/superuser hoặc được cấp quyền Điều hành giải sử dụng bàn quản lý. Admin không đăng ký hoặc nộp bot bằng tài khoản quản trị.

## Khởi động web và phân quyền

```powershell
venv/Scripts/python manage.py migrate
venv/Scripts/python manage.py provision_judges --operator TEN_TAI_KHOAN_BTC
venv/Scripts/python manage.py runserver
```

Token chỉ in khi tạo hoặc đổi; giữ riêng cho từng máy, không đưa vào Git/trình duyệt. Lệnh chạy lại giữ token đã có. Đổi bằng --rotate-slot 1 hoặc tắt bằng --disable-slot 1 khi không còn tác vụ có lease hợp lệ.

## Chuẩn bị 4 worker

Web điều phối hàng đợi trong database; bốn máy Docker riêng chủ động kết nối HTTPS để nhận việc. Mỗi máy chạy một worker với token riêng. Bốn tiến trình trên cùng máy chỉ là diễn tập, không phải bốn máy vật lý.

Dùng PostgreSQL cho giải thật; SQLite chỉ dùng local. Redis dùng chung cho cache/Channels nếu chạy nhiều web process. Worker không cần thông tin đăng nhập database hay mở cổng nhận request.

Build image một lần, phân phối bằng docker save/load và đối chiếu cùng image ID trên bốn máy:

```powershell
docker build -t ott-bot:1 sandbox
docker image inspect ott-bot:1 --format "{{.Id}}"
$env:JUDGE_WORKER_TOKEN = 'TOKEN_RIENG_CUA_MAY_NAY'
python -m matches.judge_worker --server https://TEN-MIEN-WEB
```

Nhập toàn bộ image ID sha256 vào Thiết lập mùa giải. Local có thể dùng http://127.0.0.1:8000. Docker Desktop phải chạy Engine, đồng thời worker cũng phải được khởi động. Không chạy bot trực tiếp trên host. Không đổi image hoặc release engine sau khi bắt đầu kiểm tra bài.

## Luồng mùa giải

1. Tạo mùa, đặt hạn đăng ký/nộp bài, giới hạn tài khoản và image chấm. Đại diện đăng ký trên /competition/.
2. Mở nộp bài. Đăng ký còn được nhận trong giai đoạn này tới hạn đăng ký, trước khóa bài/bốc thăm.
3. Đại diện nộp bot trên /ai/ với mã mục dự thi. Bản đầu chọn tự động; bản sau phải chọn lại. Tối đa 5 lượt kiểm tra thử/ngày/mùa.
4. Admin gửi kiểm tra các bản đã chọn. Kiểm tra cơ bản gồm một nước hợp lệ cho hai bên trên 4 bàn mẫu; không chứng minh bot đúng ở mọi trạng thái.
5. Khóa bài khi mọi mục có snapshot. Tất cả bài chính thức phải kiểm tra đạt trước thi đấu.
6. Bốc thăm: bảng tối đa 4 mục, đổi bên hai lượt, hai mục đầu bảng đi tiếp. Với 4.000 bot có 1.000 bảng và 12.000 ván vòng bảng.
7. Chuyển sang Thi đấu và đưa trận vào hàng đợi. Trận vòng sau đủ đối thủ tự được đưa vào hàng đợi.
8. Trận hòa loại trực tiếp chờ admin áp dụng quy tắc phân thắng thua đã công bố, có lý do/nhật ký; không tự chọn ngẫu nhiên người thắng.
9. Khi không còn trận/tác vụ cần xử lý, chốt trực tiếp Kết thúc. Không còn bước hay thời hạn khiếu nại.

Nếu cần sửa bài trước thi đấu, mở lại nộp bài cho toàn mùa, có lý do. Giữ lịch đối thủ nếu đã bốc thăm. Hệ thống lưu snapshot, hash và nhật ký để đối chiếu.

## Lịch sử, bài nộp và tiến độ

Trang Bài nộp được phân trang, chỉ tải source khi admin bấm Xem mã. Duyệt thủ công khác kiểm tra tự động.

Lịch sử đấu xem theo mùa và phân trang. Xem replay ngay trong hàng trận đã hoàn tất; thí sinh chỉ xem được trận của đại diện mình. Admin xem toàn mùa.

Thanh Kiểm tra Python đếm bài đã kiểm tra xong, gồm cả không đạt. Thanh Thi đấu đếm trận có kết quả trên tổng trận phải chơi, không tính bye. Lỗi máy/trận chờ xử lý chưa hoàn thành. Giao diện cập nhật khoảng 10 giây; thống kê công khai cache 5 giây.

Heartbeat 25 giây, lease 120 giây. Tác vụ hết lease có thể được máy khác nhận lại; kết quả cũ không cộng điểm hai lần. Sau ba lần hết lease, admin xem xét tác vụ lỗi. Tạm dừng ngừng nhận việc mới; tác vụ đang chạy vẫn hoàn tất.

## Dữ liệu cũ và kiểm thử

Migration chuyển các mục đội cũ sang tài khoản đội trưởng làm đại diện, giữ nguyên ID mục, bài nộp, snapshot, lịch đấu và kết quả. Hồ sơ đội/email cũ chỉ giữ làm dữ liệu lịch sử; API các chức năng đã bỏ trả 410. Lệnh gửi email cũ bị vô hiệu hóa để không gửi thư chờ ngoài ý muốn. Mùa ở bước khiếu nại cũ trở về Thi đấu để admin tự chốt.

Sao lưu database trước migration. Với PostgreSQL, thử pg_dump/pg_restore vào staging trước khi vận hành thật. File backup/source/token đặt ngoài static, trong private-exports bị Git bỏ qua.

Có thể tạo mùa diễn tập riêng (DEBUG=True):

```powershell
venv/Scripts/python manage.py rehearse_tournament --participants 4000 --image sha256:IMAGE_ID_64_KY_TU
```

Lệnh không tạo kết quả giả. Kết nối worker và đo tốc độ thực tế, thử ngắt một máy, kiểm tra tiếp tục và tính điểm không trùng. Kiểm thử SQLite/database bộ nhớ không thay thế diễn tập PostgreSQL/Redis/Docker trên bốn máy thật.
