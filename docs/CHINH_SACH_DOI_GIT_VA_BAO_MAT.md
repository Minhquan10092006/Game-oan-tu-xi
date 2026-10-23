# Chính sách đội, Git và bảo mật giải K71

## Cách nộp chính thức được chọn

**Bản source nộp trực tiếp trên web, có SHA-256 và biên nhận, là bản thi chính thức.** Đây là phương án đáng tin cậy nhất cho chấm tự động vì BTC biết chính xác từng byte sẽ được khóa và chạy.

Git là tùy chọn để đối chiếu quá trình làm bài. Khi chọn Git, người chơi vẫn phải nộp source lên web và khai báo URL HTTPS GitHub/GitLab cùng mã commit đầy đủ. Web không clone URL, không chạy `git`, không tải archive, không đọc webhook và không thực thi code từ Git. Vì vậy URL Git không thể biến thành đường vào máy chủ.

BTC so sánh SHA-256 của source nộp với file ở commit khai báo trong bước duyệt. Khi khóa giải, BTC xuất source đã lưu từ database; không clone branch, tag hay commit rút gọn. Branch như `main` có thể bị đổi nên không đủ điều kiện làm biên nhận.

## Chống giả danh đội

- Mỗi tài khoản chỉ có một mục dự thi trong một mùa: hoặc cá nhân, hoặc thuộc một đội.
- Mỗi đội có mã ngẫu nhiên `K71-...`; database chỉ lưu SHA-256 của mã, không lưu mã rõ.
- Mã chỉ trả về một lần cho đội trưởng lúc lập đội hoặc đổi mã. Đội trưởng phải gửi qua kênh riêng cho thành viên.
- Chỉ đội trưởng được nộp bot chính thức gắn với đội. Thành viên vẫn có thể nộp bài luyện tập của riêng mình.
- BTC khóa thành viên, mã đội và mục dự thi trước khi xuất bài. Sau khi khóa, không thay người hoặc thay bot qua web.

Mã đội xác nhận quyền tham gia kỹ thuật, không thay thế xác nhận danh sách thành viên của BTC. Trước giải, BTC đối chiếu mã sinh viên, danh sách đội và đội trưởng theo quy định của khoa.

## Ranh giới an toàn

1. Web chỉ nhận text source, giới hạn 64 KiB, kiểm tra cú pháp và lưu biên nhận. Web không import hay gọi source nộp.
2. Máy chấm riêng mới chạy bot. Mỗi lượt tạo container không mạng, non-root, read-only, cap-drop, no-new-privileges, giới hạn RAM/CPU/PID/file/output và mount duy nhất file bot read-only.
3. Máy chấm không công khai Internet, không giữ secret web, token cloud hoặc Docker socket cho web.
4. Docker không phải biên giới tuyệt đối. Giải thật cần máy/VM riêng đã vá, image được khóa sau diễn tập, quyền quản trị hạn chế và kiểm tra khôi phục.
5. Không đưa stderr/raw replay chứa dữ liệu do bot in ra công khai trước khi BTC lọc.

## Kiểm thử đang có

- CSRF cho request thay đổi dữ liệu.
- Tài khoản khách không thể đăng ký giải, lập đội, vào đội hay nộp bài.
- Không thể dùng mã sai để biết tên đội.
- Không thể đăng ký cá nhân sau khi đã vào đội, hoặc vào đội sau khi đã đăng ký cá nhân.
- Thành viên và người ngoài không thể nộp bot thay đội trưởng.
- Từ chối Git URL dùng `file:`, host ngoài danh sách, URL có token/query/fragment và commit không đầy đủ.
- API demo web không chạy code người dùng; máy chấm chỉ chạy Docker, không fallback sang Python host.
- Runner kiểm tra giới hạn mạng, quyền, RAM, PID, output và timeout bằng regression test.

Các test này không chứng minh không còn mọi lỗ hổng. Trước giải thật cần diễn tập Docker trên máy chấm thực tế, quét dependency, kiểm thử tải, backup/restore và rà soát độc lập bởi cán bộ phụ trách hạ tầng.
