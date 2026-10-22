# Giao diện Retro K71

## Các trang

- `/`: trang chủ công khai, banner, slogan, luật tóm tắt và hướng dẫn tham gia.
- `/register/`: đăng ký tài khoản; chưa đồng nghĩa đăng ký giải chính thức.
- `/login/`: đăng nhập hoặc trải nghiệm bằng tài khoản khách.
- `/play/`: chọn chế độ chơi sau khi đăng nhập.
- `/battlecode/`: chạy bot mẫu và xem lại từng nước, điều chỉnh tốc độ hoặc kéo thanh tiến trình.

## Tổ chức mã nguồn

- `web/templates/web/retro/base.html`: khung trang chung.
- `retro/header.html`, `retro/footer.html`: thương hiệu và điều hướng dùng chung.
- `web/static/web/css/retro.css`: biến màu, font, viền nổi/chìm và thành phần dùng chung. Sửa token tại đây khi thay đổi nhận diện.
- `retro-play.css`: lớp giao diện cho màn chơi hiện có.
- `retro-arena.css`: bố cục phòng bot mẫu và bàn cờ phát lại.
- `web/static/web/js/retro.js`: bật/tắt hiệu ứng, lưu lựa chọn trên trình duyệt.
- `retro-arena.js`: tải trận mẫu, phát/dừng, tua từng nước và lịch sử.

Giao diện dùng CSS và font hệ thống, không tải thêm thư viện hay font ngoài. Hiệu ứng tự dừng theo `prefers-reduced-motion`; người dùng có nút dừng hiệu ứng. Liên kết, biểu mẫu và nút dùng HTML ngữ nghĩa với trạng thái focus cho bàn phím.

## Kiểm tra đã thực hiện

20 bài kiểm thử cho trang công khai, đăng nhập/đăng ký, chuyển hướng, CSRF, quyền truy cập trận mẫu và biên nhận bài nộp đã đạt. Hai tệp JavaScript mới đã qua kiểm tra cú pháp Node. HTTP local xác nhận các trang và tài nguyên tải thành công, tạo trận mẫu trả 201, đọc bản phát lại trả 200.

Chưa kiểm tra trực quan bằng trình duyệt trong môi trường thực thi này. Trước khi trình diễn chính thức, kiểm tra bố cục trên desktop và điện thoại, điều khiển phát lại và thao tác bàn phím. Các trang quản trị, nộp bài và lịch sử vẫn dùng bố cục hiện có.
