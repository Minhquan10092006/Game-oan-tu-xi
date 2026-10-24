# Luật thi đấu và sơ đồ giải Oẳn Tù Tì K71

**Bản đề xuất cho hệ thống demo.** Ban tổ chức cần phê duyệt thể lệ, lịch và thời hạn trước khi công bố giải chính thức. Các trận bot chính thức phải được chấm trên máy chấm riêng; website chỉ lưu đăng ký, bốc thăm, bảng xếp hạng và kết quả từ máy chấm.

## 1. Luật bàn cờ

- Bàn cờ có 9 hàng × 9 cột; tọa độ bắt đầu từ `(1, 1)`, hàng tăng từ trên xuống và cột tăng từ trái sang phải.
- Mỗi bên có 3 quân Kéo, 3 quân Búa và 3 quân Bao. P1 ở góc trên trái và đi trước; P2 ở góc dưới phải.
- P1 thắng khi một quân đến `(9, 9)`; P2 thắng khi một quân đến `(1, 1)`.
- Mỗi lượt đi đúng một quân một ô theo một trong tám hướng. Không đi ra ngoài bàn, không vào ô có quân cùng bên và không bỏ lượt.
- Búa bắt Kéo, Kéo bắt Bao, Bao bắt Búa. Hai quân cùng loại chặn nhau. Quân bị bắt bị loại khỏi bàn.
- Một bên thắng ngay khi đến đích, bắt hết một loại quân của đối thủ hoặc khiến đối thủ không còn nước đi hợp lệ.
- Hòa nếu một trạng thái bàn cờ lặp lần thứ ba hoặc đạt 300 nước đơn mà chưa có bên thắng. Điều kiện thắng được xét trước điều kiện hòa.
- Mẫu bot giải đấu nhận JSON qua stdin, trả một JSON hợp lệ qua stdout; giao thức đầy đủ và cấu hình sandbox xem tại [LUAT_THI_DAU_K71.md](./LUAT_THI_DAU_K71.md).

## 2. Đơn vị dự thi và đăng ký

- Mỗi nhóm dùng một tài khoản sinh viên đại diện, tương ứng một **mục dự thi** trong mỗi mùa. Web không quản lý danh sách thành viên.
- Đại diện đăng ký và theo dõi thông báo trực tiếp trên web; không yêu cầu email.
- Tài khoản đại diện đăng ký, nộp và chọn bot chính thức. Các sinh viên làm nhóm ngoài web, không cần mã mời hay gia nhập đội.
- Khi admin chốt danh sách và bốc thăm, danh sách dự thi được khóa. Bốc thăm không thể chạy lại để tránh thay đổi bảng sau khi đã công bố.

## 3. Bốc thăm vòng bảng

1. BTC xác nhận đăng ký đã đóng và rà soát danh sách. Tài khoản đại diện trùng, rút lui hoặc chưa hoàn tất thông tin cần được xử lý trước khi bốc thăm.
2. Admin bấm **Bốc thăm chia bảng** trong trang quản trị. Website khóa danh sách đăng ký, trộn ngẫu nhiên các mục bằng seed được lưu cùng mùa giải và chia đều vào các bảng.
3. Mỗi bảng có tối đa 4 mục. Số bảng là `ceil(số mục dự thi / 4)`; phần dư được chia đều để kích thước các bảng chênh nhau nhiều nhất một mục.
4. Bảng được đặt tên A, B, C…; sau Z tiếp tục AA, AB… Mỗi cặp trong bảng gặp nhau hai ván, đổi bên P1/P2.
5. Thắng được 3 điểm, hòa 1 điểm, thua 0 điểm. Sau khi BTC nhập đủ kết quả, thứ hạng lần lượt xét: tổng điểm, số trận thắng, điểm đối đầu trong nhóm đồng điểm và đồng thắng; nếu vẫn bằng nhau, dùng kết quả bốc thăm phụ xác định trước từ seed để phân hạng ổn định.
6. Hai mục đứng đầu mỗi bảng vào nhánh loại trực tiếp. Nhánh được xếp ngẫu nhiên, ưu tiên ghép khác bảng ở vòng đầu; nếu số suất không đủ lũy thừa hai, các suất **BYE** được phân ngẫu nhiên và tự đi tiếp.

### Minh họa quy mô World Cup 48 đội

Nút **Xem demo World Cup · 48 đội** ở trang giải đấu tạo một sơ đồ minh họa ngẫu nhiên chỉ trong trình duyệt:

- 48 đội được chia thành 12 bảng × 4 đội. Bảng điểm ví dụ đánh dấu hai đội đầu mỗi bảng.
- 8 đội hạng ba tốt nhất trong dữ liệu minh họa cũng được đánh dấu đi tiếp, tạo vòng 32 đội.
- Nhánh loại trực tiếp có 16 trận vòng 32, 8 trận vòng 16, 4 tứ kết, 2 bán kết và 1 chung kết (31 trận).
- Sơ đồ chia thành hai nhánh trái/phải; các vòng thu dần về trận chung kết ở giữa.
- Tên đội, bảng điểm và nhánh đấu đều là dữ liệu giả; làm mới/trộn demo không tạo tài khoản, không ghi cơ sở dữ liệu và không gửi thông báo thật.

**Đây là demo thể thức 48 đội, không thay đổi luật bốc thăm thật đang cấu hình trong website.** Bốc thăm mùa giải thật vẫn dùng danh sách đã đăng ký, tối đa 4 mục mỗi bảng và đưa hai mục đầu từng bảng vào nhánh; việc chọn 8 đội hạng ba tốt nhất chưa được tích hợp vào bộ bốc thăm hoặc công cụ chấm offline. BTC cần duyệt một thể thức thống nhất trước khi công bố giải chính thức.

## 4. Sơ đồ các vòng

```text
ĐĂNG KÝ
   │ BTC chốt danh sách và bốc thăm ngẫu nhiên
   ▼
VÒNG BẢNG (nhóm tối đa 4 · vòng tròn hai lượt · 3/1/0 điểm)
   │ Hai mục đầu mỗi bảng
   ▼
VÒNG LOẠI TRỰC TIẾP (ghép nhánh · có BYE nếu cần)
   ├── Thua bán kết ──► Tranh hạng ba
   └── Thắng bán kết ─► Chung kết ─► Nhà vô địch
```

Số vòng loại trực tiếp tự điều chỉnh theo số suất đi tiếp. Sơ đồ 48 đội phía trên là demo riêng; bốc thăm thật hiện tự tạo nhánh từ các mục thực tế đã đăng ký.

## 5. Công bố bảng và cập nhật kết quả

- Sau khi bốc thăm, trang **Đăng ký mùa giải** hiển thị tên bảng, thành viên, thứ hạng tạm thời, lịch các cặp và sơ đồ nhánh tới chung kết.
- Thứ hạng bắt đầu ở 0 điểm và chỉ đổi sau khi BTC lưu kết quả ván. Website không tự chạy bot sinh viên hoặc tự xác nhận kết quả thi đấu.
- Khi đã nhập đủ kết quả vòng bảng, hệ thống đưa hai mục đầu mỗi bảng vào nhánh. Kết quả loại trực tiếp đưa người thắng sang trận kế tiếp; kết quả bán kết cũng đưa người thua vào trận tranh hạng ba.
- Thông báo được đăng trực tiếp trong Tổng quan của mùa giải. Không có luồng gửi email.
- Admin đăng thông báo trên web và kiểm tra danh sách bài/kết quả trước khi chốt.

## 6. Trách nhiệm và giới hạn

- BTC phải kiểm tra danh sách, seed, kết quả và sơ đồ trước khi thông báo chính thức.
- Việc nhập kết quả trong web là thao tác của admin, không thay thế biên bản chấm, log, replay và nhật ký xử lý sự cố.
- Thể lệ về sandbox, giới hạn tài nguyên, nộp bài, sự cố được nêu đầy đủ trong [luật thi đấu K71](./LUAT_THI_DAU_K71.md). Quy định điểm và xếp hạng xem [chấm điểm và xếp hạng](./CHAM_DIEM_XEP_HANG.md).
