# Kế hoạch vận hành cao điểm 4.000 người

Mục tiêu là phục vụ tối đa 4.000 người có thể truy cập cùng lúc trong giờ cao điểm để xem thông tin, đăng nhập và nộp bài. Đây là mục tiêu cần kiểm thử trước giải; tài liệu này không khẳng định bản demo hiện tại đã đạt mức đó.

## Quyết định kiến trúc

```text
Trình duyệt sinh viên → Web Django → PostgreSQL
                         │
                         └→ Redis: phiên realtime và trạng thái dùng chung

BTC xuất bài đã duyệt → Máy chấm riêng của trường → Docker sandbox
                                                → kết quả và replay → BTC công bố
```

Web không có Docker socket, không có quyền chạy file Python do sinh viên nộp và không có secret của máy chấm. Máy chấm không nhận request trực tiếp từ Internet. BTC chuyển gói bài đã duyệt qua kênh nội bộ được kiểm soát.

## Luồng ngày thi

1. Sinh viên đăng nhập và nộp source qua web. Web kiểm tra kích thước, số phiên bản và trả biên nhận SHA-256.
2. Hết hạn nộp, BTC chốt danh sách và chạy `export_competition_entries`. Gói xuất gồm `entries.json`, source UTF-8 và `receipts.json`.
3. Gói bài được chép sang máy chấm; BTC đối chiếu số đội, deadline và SHA-256.
4. Trên máy chấm, BTC khóa giải bằng `python -m matches.tournament freeze ...`. Lệnh lưu hash engine, hash bot, image Docker, luật và lịch đấu vào `manifest.json`.
5. Máy chấm chạy từng ván trong Docker. Mỗi bot chỉ nhận trạng thái và trả nước đi; không mạng, không chạy trên web.
6. Kết quả mỗi ván ghi độc lập. Nếu hạ tầng lỗi, ván không được cộng điểm và BTC xử lý rồi chạy tiếp.
7. Khi đủ ván, BTC xuất bảng xếp hạng và kiểm tra replay trước khi công bố.

## Chuẩn bị web cho cao điểm

- Dùng PostgreSQL trả phí có backup; không dùng SQLite hoặc database miễn phí hết hạn cho giải thật.
- Dùng Redis dùng chung cho WebSocket khi chạy nhiều tiến trình web. `InMemoryChannelLayer` hiện chỉ phù hợp một tiến trình demo.
- Đặt reverse proxy hoặc nền tảng có TLS, nén static và giới hạn request tại biên. Static CSS/JS nên được cache; không cache trang đăng nhập, bài nộp, biên nhận hay replay riêng.
- Tăng số tiến trình web chỉ sau khi Redis được cấu hình. Không chạy bot hoặc tác vụ chấm trong các tiến trình web.
- Mở nộp bài sớm, thông báo rõ thời hạn và giữ biên nhận để tránh dồn thao tác vào phút cuối.

## Diễn tập bắt buộc

Diễn tập trên đúng cấu hình dự kiến dùng cho giải, với dữ liệu giả. Theo dõi p95/p99 thời gian phản hồi, tỉ lệ 4xx/5xx, CPU, RAM, số kết nối DB, độ trễ Redis và dung lượng DB.

| Tình huống | Mục tiêu kiểm tra |
| --- | --- |
| 4.000 lượt xem trang chủ/luật | Static cache và web không lỗi 5xx |
| Đợt đăng nhập đồng thời | Session và PostgreSQL không cạn kết nối |
| Đợt nộp bài gần deadline | Biên nhận trả đúng một lần, không mất version |
| Kết nối realtime | Redis chia sẻ trạng thái giữa các tiến trình |
| Ngắt một web process | Người dùng có thể tải lại và tiếp tục thao tác |
| Ngắt máy chấm giữa giải | Không tính trùng ván, có thể resume |

Chỉ chốt số máy web, RAM và chi phí sau khi diễn tập. Báo cáo diễn tập phải ghi rõ mức request/giây, tỷ lệ nộp bài, cấu hình máy và kết quả, thay vì chỉ ghi "4.000 người".

## Máy chấm và thể thức

Nếu có 4.000 đội, không chạy vòng tròn toàn bộ vì sẽ có 15.996.000 ván hai lượt. BTC cần duyệt thể thức chia bảng hoặc số vòng giới hạn trước khi đo máy chấm. Số máy chấm được tính từ thời gian đo một ván trong Docker, số ván thực tế, thời hạn hoàn thành và dự phòng chạy lại.

## Điều kiện mở giải

1. Có người chịu trách nhiệm web, máy chấm và công bố kết quả.
2. Có backup đã thử phục hồi cho PostgreSQL, gói bài đã khóa và kết quả.
3. Có kết quả diễn tập tải web và diễn tập sandbox trên máy chấm.
4. Có quy trình tạm dừng, ghi nhận sự cố, chạy lại và khiếu nại.
5. Không thay đổi luật, image Docker hoặc release giữa lúc giải đang chạy.
