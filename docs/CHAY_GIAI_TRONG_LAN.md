# Tổ chức giải khi không có Internet

Máy giáo viên giữ web Django, `db.sqlite3` (tài khoản, bài nộp, hàng đợi,
kết quả/replay) và sandbox. Sinh viên chỉ cần trình duyệt, không cài Docker.
Cả lớp cùng kết nối router hoặc mạng dây; router không cần kết nối Internet.
Đây là chế độ một máy cho lớp học, chưa có cam kết phục vụ 4.000 máy đồng thời.

## Chuẩn bị một lần khi còn Internet

1. Cài Python và thư viện dự án theo README; dùng virtualenv hiện có.
2. Trên Windows, cài/mở Docker Desktop. Chuẩn bị image:
   `docker build -t ott-bot:1 sandbox`. Trên Linux có thể dùng Isolate đã cài
   và cấp quyền thay thế. Giữ nguyên cơ chế sandbox, không chạy bot trực tiếp trên host.
3. Tạo tài khoản admin nếu chưa có: `python manage.py createsuperuser`.
   Chuẩn bị tài khoản sinh viên, mùa giải và dữ liệu trên **database local này**.
   Dữ liệu từ web đã deploy không tự xuất hiện trên máy giáo viên.
4. Chạy `ipconfig`, chọn IPv4 của card mạng nối router lớp, ví dụ `192.168.1.10`.
   Đặt DHCP reservation trên router để IP này ổn định. Tắt AP/client isolation
   nếu router ngăn các máy trong lớp liên lạc với nhau.

## Mỗi buổi học

Trong thư mục dự án, dùng Python của virtualenv:

```powershell
.\venv\Scripts\python.exe run_classroom.py --address 192.168.1.10 --check-only
.\venv\Scripts\python.exe run_classroom.py --address 192.168.1.10
```

Đổi IP theo máy giáo viên. Cổng mặc định 8000, có thể thêm `--port 8001` nếu cổng
đang được dùng. Dừng server local cũ trước khi chạy chế độ này để tránh hai bộ chấm
cùng hoạt động. Nếu Firewall hỏi, cho phép Python trên **Private network**.
Nếu vẫn bị chặn, giáo viên/IT mở TCP 8000 inbound chỉ cho LocalSubnet trên mạng Private.
Không cần mở cổng router ra Internet.

Sinh viên mở `http://192.168.1.10:8000/`, đăng nhập, đăng ký mùa và nộp bot.
Admin mở cùng địa chỉ để quản lý giải, khóa bài và chạy giải như bình thường.
Chấm kiểm tra/trận chỉ bắt đầu khi đã tạo tác vụ bằng các chức năng hiện có;
nhận bài không đồng nghĩa lập tức tính điểm chính thức.

Lệnh khởi động kiểm tra sandbox và image đã có sẵn, cập nhật database, gom static
về máy và chạy một bộ chấm liên tục. Không tự tải image khi diễn tập mất mạng.
Chế độ này luôn dùng SQLite/cache/WebSocket/email local, không dùng database,
Redis hay SMTP bên ngoài được khai báo trong `.env`. Khóa phiên được tạo tự động
tại `private-exports/classroom-secret.key`, không đưa lên GitHub.

Giữ cửa sổ lệnh và Docker/Isolate hoạt động; tắt sleep máy giáo viên. Hàng đợi
chấm nằm trong database; khởi động lại cùng lệnh sẽ nhận việc đang chờ.
Việc bị ngắt khi đang chấm cần đợi lease hết hạn rồi được xử lý lại theo cơ chế
hiện tại; không đảm bảo tiếp tục ngay tại nước đi bị ngắt.
Sau buổi học, dừng server/chấm trước khi sao lưu `db.sqlite3` và giữ các tệp
`private-exports/`, `tournament-data/` nếu có. Không xóa database để khởi động lại.

## Khi xảy ra sự cố mạng

| Tình huống | Hệ thống xử lý |
| --- | --- |
| Mất Internet, LAN vẫn còn | Nộp bài, chấm, xem kết quả/replay vẫn dùng máy giáo viên. |
| Sinh viên mất cả LAN | Trang đang mở lưu nháp và bản nộp vào IndexedDB. Chưa có biên nhận thì chưa nộp thành công. |
| Kết nối lại LAN | Giữ/mở trang đúng địa chỉ và đúng tài khoản; bài chờ tự gửi, cùng mã biên nhận tránh tạo bài trùng. Có nút Gửi lại bài chờ. |
| Máy giáo viên tắt | Không nhận/chấm được. Khởi động lại máy, sandbox và lệnh trên. |

**Giới hạn HTTP LAN:** trình duyệt không cho Service Worker ở địa chỉ
`http://192.168...`. Nháp và hàng đợi vẫn lưu, nhưng **giữ tab Nộp AI mở khi
mất LAN**, không reload/đóng tab. Tải `.py` dự phòng. Muốn mở lại trang khi mất
LAN cần triển khai HTTPS với chứng chỉ được từng máy sinh viên tin cậy, truy cập
trước và đợi báo sẵn sàng offline. Lệnh này chưa tự cấp chứng chỉ HTTPS.
Đổi IP/cổng/giao thức sẽ tạo origin khác: dữ liệu local cũ không tự chuyển sang.

Hạn nộp tính theo giờ máy giáo viên nhận bài, không tin đồng hồ sinh viên.
Nếu sự cố kéo dài, admin chủ động gia hạn trước khi nhận bài gửi lại.
Nếu cả LAN không phục hồi, tải file `.py` rồi chuyển bằng USB/mạng dây dự phòng;
bản này chưa có chức năng admin nhập bài hộ từ USB.

## Diễn tập trước vòng chung kết

1. Mở web từ **máy sinh viên thật**, đăng nhập và nộp một bot.
2. Rút dây WAN của router (giữ Wi-Fi/LAN), nộp bot khác, chạy kiểm tra và một trận;
   xem kết quả và replay từ máy sinh viên.
3. Tắt Wi-Fi ở máy sinh viên, giữ tab Nộp AI mở, sửa rồi bấm Nộp bài.
   Kiểm tra bài có trong hàng đợi và tải được `.py`.
4. Bật lại Wi-Fi: kiểm tra có biên nhận server, chỉ một bài được tạo; thử lại không
   tạo thêm phiên bản. Kiểm tra tình huống hết phiên/hết hạn để hướng dẫn lớp.
5. Thử dừng/khởi động server, xác nhận dữ liệu và hàng đợi vẫn còn.

Chỉ dùng cho giải thật sau khi diễn tập trên router và máy dự kiến sử dụng.
