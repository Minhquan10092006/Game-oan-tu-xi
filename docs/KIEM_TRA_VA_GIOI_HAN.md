# Biên bản kiểm tra và giới hạn — 19/10/2026

## Thay đổi chính

- Sửa luật loại hết một loại quân trong engine bot, engine Python cũ và engine JavaScript người chơi.
- Engine bot kiểm tra tọa độ đúng kiểu, từ chối đi sau kết thúc, ưu tiên thắng trước hòa, lặp trạng thái không phụ thuộc ID quân cùng loại.
- Thay subprocess trực tiếp bằng Docker runner trên máy chấm riêng; không có fallback host. Chặn output ngay khi đang đọc và giới hạn bộ nhớ buffer.
- Demo web chỉ dùng chiến thuật mẫu trong dự án; file sinh viên không được thực thi trên web. Bật lại CSRF cho các endpoint thay đổi trạng thái.
- Replay API kiểm tra chủ trận/admin. Lỗi ghi lịch sử không được báo thành công. Trận mẫu không gắn mùa giải chính thức.
- Hash bài và biên nhận trong API/giao diện; bảo toàn khoảng trắng mã nộp, hạn mức ngày, tuần tự hóa cấp version trên PostgreSQL.
- Xuất bài đã duyệt kèm biên nhận, khóa source/engine/image, lịch hai lượt, lưu từng ván nguyên tử, phân loại lỗi hạ tầng, resume và xếp hạng local.
- ELO trên web được ghi rõ là luyện tập. Bot mẫu và hướng dẫn trên trang nộp bài dùng giao thức K71.

## Đã kiểm tra

- 22 kiểm thử lõi độc lập Django: luật, xếp hạng, schedule, khóa bài, retry, chống ghi điểm trùng, lỗi hạ tầng và cấu hình lệnh Docker.
- 78 kiểm thử Django cho engine hiện có, demo, CSRF, quyền replay, lỗi DB, biên nhận, quota, xuất bài và API submissions.
- Django system check không báo lỗi; `git diff --check` không có lỗi whitespace.
- Các test dùng dữ liệu tạm/DB trong bộ nhớ. `db.sqlite3` đã có thay đổi từ trước phiên làm việc và không được sửa bởi quá trình kiểm tra này.

## Chưa xác nhận trên hạ tầng thật

- Docker CLI có trên máy nhưng Docker daemon chưa chạy. Kiểm thử Docker hiện giả lập lời gọi; chưa chứng minh container thực tế chạy được hay chặn được mọi hành vi xấu.
- Chưa benchmark thời gian tạo container/mỗi nước, tải đồng thời, CPU burst hoặc chi phí giải thật.
- Chưa kiểm tra giao dịch đồng thời trên PostgreSQL; test hiện dùng SQLite.
- Chưa chạy diễn tập mất điện, phục hồi backup hoặc kiểm tra bảo mật độc lập.
- Chưa deploy các thay đổi lên Render, chưa tạo tài nguyên cloud trả phí.

## Giới hạn thiết kế V1

Công cụ giải chạy một coordinator tuần tự, dữ liệu file riêng cho BTC; chưa có dashboard giải tự động, queue phân tán, tự chia bảng hoặc công bố theo lịch trên web. Việc chọn bài trước deadline, kiểm tra danh tính, phê duyệt khiếu nại, chia bảng và công bố vẫn do BTC thực hiện theo tài liệu.

Docker là lớp cách ly cơ bản, không thay thế máy chấm chuyên dụng và việc vá bảo mật. Image phải được build, kiểm tra và khóa trên máy chấm trước thi. Giới hạn CPU hiện áp theo tiến trình cộng giới hạn container/wall time; không phải phép đo CPU tổng chính xác cho cả cây tiến trình.

Chức năng người chơi realtime vẫn dùng bộ nhớ tiến trình và không phải engine chính thức của giải bot. Không tăng nhiều web process cho phòng realtime trước khi sửa cơ chế chia sẻ trạng thái.

Chỉ được coi là sẵn sàng cho giải thật sau các bước diễn tập trong [kế hoạch vận hành](HOST_DEMO_VA_VAN_HANH.md).
