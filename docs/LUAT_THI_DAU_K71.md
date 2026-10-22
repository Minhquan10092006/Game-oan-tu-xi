# THỂ LỆ GIẢI OẲN TÙ TÌ 2.0 — K71

**Phiên bản đề xuất: k71-v1.0 · Ngày soạn: 19/10/2026.**

Tài liệu để nhà trường xem xét, phê duyệt và công bố trước khi mở đăng ký. Các thông số dưới đây là cấu hình đề xuất thống nhất của bản triển khai; không phải quyết định đã được nhà trường ban hành. BTC điền ngày thi, hạn nộp, hình thức cá nhân/đội, người phụ trách và giải thưởng trước khi công bố.

## 1. Mục tiêu và đối tượng

Sinh viên K71 viết chương trình Python điều khiển quân cờ. Hệ thống tự thực thi chương trình, kiểm tra nước đi và lưu diễn biến. Thành tích phản ánh kết quả thi đấu theo cùng luật và cùng giới hạn tài nguyên.

Mỗi đơn vị dự thi có một mã đội duy nhất, danh sách thành viên/MSSV đã xác minh và một bài thi chính thức cho mỗi giai đoạn được phép khóa bài. Mặc định mỗi sinh viên chỉ thuộc một đội. Số thành viên tối đa do BTC công bố khi mở đăng ký; không thay đổi sau khi đóng đăng ký.

## 2. Bàn cờ và bố trí ban đầu

- Bàn 9 hàng × 9 cột; tọa độ `(hàng, cột)` bắt đầu từ **1**.
- Hàng tăng từ trên xuống, cột tăng từ trái sang phải.
- Mỗi bên có 9 quân: 3 Kéo, 3 Búa, 3 Bao. Mọi quân đều được nhìn thấy.
- P1 đi trước. P1 thắng khi đến `(9,9)`; P2 thắng khi đến `(1,1)`.
- Không có ô cấm, quân ẩn, phong cấp, hồi sinh hay yếu tố ngẫu nhiên trong luật bàn cờ.
- Các bàn chữ thập, chữ nhật và có chướng ngại chỉ dùng thử nghiệm; không dùng cho giải K71 phiên bản này.

Ký hiệu `K` = Kéo, `B` = Búa, `Ba` = Bao. Các ô khác để trống.

| P1 | Cột 1 | Cột 2 | Cột 3 |
|---|---|---|---|
| Hàng 1 | K | B | Ba |
| Hàng 2 | Ba | K | B |
| Hàng 3 | B | Ba | K |

P2 là bố trí P1 quay 180°:

| P2 | Cột 7 | Cột 8 | Cột 9 |
|---|---|---|---|
| Hàng 7 | K | Ba | B |
| Hàng 8 | B | K | Ba |
| Hàng 9 | Ba | B | K |

Ô đích ban đầu có quân đối phương. Không được bỏ qua luật chiếm ô khi đi vào đích.

## 3. Di chuyển và bắt quân

1. Hai bên đi luân phiên. Mỗi nước di chuyển đúng một quân của bên đến lượt.
2. Quân đi đúng một ô theo một trong tám hướng: ngang, dọc hoặc chéo. Không được đứng yên, bỏ lượt hoặc đi nhiều ô.
3. Không được đi ra ngoài bàn hoặc vào ô có quân cùng bên.
4. Được đi vào ô trống. Với ô có quân đối phương, chỉ được đi vào nếu quân đang đi thắng quân trên ô đó:
   - Búa bắt Kéo.
   - Kéo bắt Bao.
   - Bao bắt Búa.
5. Hai quân cùng loại chặn nhau. Không được đi vào quân khắc chế mình; không có nước đi tự hi sinh.
6. Quân bị bắt bị loại vĩnh viễn. Quân đi chiếm ô vừa bắt.
7. Đi chéo không phụ thuộc hai ô kề ngang/dọc; chỉ kiểm tra ô xuất phát và ô đích.
8. Game Engine là cơ quan xác nhận nước hợp lệ. Trình duyệt và chương trình sinh viên không quyết định kết quả.

## 4. Thắng, thua và hòa

Sau một nước hợp lệ, kiểm tra theo thứ tự:

1. **Đến đích:** quân vừa đi tới ô đích của bên mình → thắng.
2. **Loại một loại quân:** bắt quân cuối cùng thuộc bất kỳ một loại của đối phương → thắng ngay. Ví dụ đối thủ mất hết 3 quân Kéo thì thua dù vẫn còn Búa và Bao.
3. **Đối phương không còn nước hợp lệ:** bên vừa đi thắng; không cho bỏ lượt.
4. **Lặp trạng thái lần thứ ba:** hòa. Trạng thái gồm bên đến lượt và vị trí/loại/chủ sở hữu các quân; không phân biệt mã định danh giữa các quân cùng loại, không tính bộ nhớ nội bộ bot. Trạng thái khởi đầu được tính một lần.
5. **Đủ 300 nước đơn:** hòa nếu chưa thỏa điều kiện trước đó. Một nước đơn là một lần một bên đi; 300 nước đơn tương ứng tối đa 150 lượt mỗi bên.

Điều kiện thắng được ưu tiên hơn hòa nếu cùng xuất hiện ở nước thứ 300. Không cộng điểm theo số quân bắt được hoặc số quân còn lại.

## 5. Giao thức chương trình Python

- Nộp một file `.py`, UTF-8, tối đa **65.536 byte (64 KiB)**. Thư viện chuẩn Python 3.12; không tự cài gói hoặc tải dữ liệu lúc thi.
- Mỗi nước khởi chạy một tiến trình mới trong môi trường cách ly mới. Không dựa vào file từ nước trước; lưu bộ nhớ qua `userdata` nếu cần.
- Đọc một JSON từ stdin đến EOF, trả đúng một JSON ra stdout rồi thoát mã 0. Thông tin debug ghi stderr.
- Input có `protocol_version`, `match_id`, `current_player`, `board`, `players`, `legal_moves`, `ply`, `turn`, `userdata`.
- `current_player` là `P1` hoặc `P2`. Tọa độ trong giao thức chính thức luôn từ 1 đến 9.
- `legal_moves` hỗ trợ người mới; bot vẫn phải chọn đúng nước, không được tự công bố thắng.
- Output tối thiểu:

```json
{"move":{"piece_id":"P1-R1","from":[1,2],"to":[2,3]},"userdata":null}
```

Ví dụ trên chỉ minh họa cấu trúc; không bảo đảm hợp lệ ở bàn ban đầu. Bot mẫu nên lấy một nước trong `legal_moves`.

`from` và `to` phải là mảng đúng hai số nguyên; boolean, số thực và chuỗi không được chấp nhận. JSON không có khóa trùng, NaN hoặc Infinity. `userdata` tùy chọn, tối đa 4 KiB sau tuần tự hóa JSON UTF-8 bằng bộ chấm. Stdout và stderr tối đa 64 KiB mỗi luồng mỗi nước.

## 6. Tài nguyên và lỗi bot

Thông số đề xuất cần được BTC diễn tập trên máy chấm rồi cố định trước khi khóa bài:

| Tài nguyên | Giới hạn của runner V1 |
|---|---|
| RAM và swap | Container 256 MiB, không cấp thêm swap |
| Năng lực CPU | Tối đa 1 CPU/container |
| CPU của mỗi tiến trình | 2 giây bằng giới hạn hệ điều hành; đây không phải bộ đếm CPU tổng của toàn bộ cây tiến trình |
| Thời gian một nước | 5 giây kể từ gọi thực thi trong container đã khởi động, gồm giao tiếp thực thi; không tính tạo container |
| Tiến trình/luồng | Tối đa 32 trong container |
| File tạm | `/tmp` tối đa 8 MiB; giới hạn mỗi file ghi 64 KiB |
| Mạng | Không truy cập Internet, mạng nội bộ, metadata của host |
| Quyền | Không root, không quyền nâng cấp; filesystem gốc chỉ đọc |

Mọi đội dùng cùng image Python đã khóa, cùng loại máy và giới hạn. Chỉ chạy mức song song đã được kiểm tra không gây tranh chấp CPU/RAM. Giới hạn wall time là giới hạn cuối cùng cho toàn bộ lượt, kể cả bot tạo tiến trình con.

Nước sai, JSON sai, quá thời gian, vượt output hoặc chương trình thoát lỗi do chính bot → thua ván đó. Không tự sửa nước hoặc chọn nước thay bot.

Mất máy chấm, lỗi Docker, mất dịch vụ lưu trữ, thiếu image hoặc không xác định được nguồn lỗi → **chưa có kết quả**, không cộng điểm cho ai. BTC giữ log, kiểm tra và chạy lại toàn bộ ván với đúng bài, engine, image đã khóa. Replay lần lỗi vẫn được giữ. Nếu hạ tầng gây ảnh hưởng rộng, BTC tạm dừng lịch chấm.

Không thể suy ra mọi nguyên nhân hạ tầng chỉ từ exit code. Kết quả timeout/crash bất thường hàng loạt phải được BTC đối chiếu tình trạng máy trước khi công bố.

## 7. Nộp, kiểm tra và khóa bài

1. Sinh viên đăng nhập tài khoản đã đăng ký, gửi mã Python; hệ thống trả mã bài, phiên bản, thời gian server nhận và SHA-256.
2. “Đã nhận bài” nghĩa là lưu thành công; “đã duyệt” là kiểm tra ban đầu, chưa có nghĩa đạt giải hoặc sandbox đã bảo đảm an toàn tuyệt đối.
3. Mặc định tối đa 50 lần nộp/tài khoản/ngày theo giờ Việt Nam. Mọi thay đổi quota phải công bố chung trước thi.
4. Trước hạn chót, đội xác nhận một bài chính thức. Nếu không xác nhận, đề xuất chọn bản đã được BTC xác nhận đạt kiểm tra gần nhất trước hạn; BTC phải ghi rõ chính sách này khi công bố giải.
5. BTC xuất bản chính thức, kiểm tra hash, sao lưu và khóa manifest. Không sửa nội dung file đã khóa. Duyệt lại một bài trong web không thay đổi manifest đã khóa.
6. Manifest lưu mã đội, tên, hash bài, phiên bản engine/runner, image ID, giới hạn và lịch đấu. BTC giữ bản sao ngoài máy chấm và gửi biên nhận hash bài cho từng đội.
7. Sau khóa bài, mọi thay đổi luật/engine phải có thông báo, phiên bản mới và quyết định xử lý toàn bộ các ván bị ảnh hưởng; không âm thầm sửa một ván.

Link Git chỉ là kênh bổ sung khi BTC cho phép. Phải chỉ định commit, lấy nội dung và cấp biên nhận trước hạn. Không chấm từ một nhánh Git có thể thay đổi sau hạn.

## 8. Mất mạng và nộp dự phòng

- File/bản nháp lưu trên máy sinh viên chưa được coi là đã nộp.
- Giờ đồng hồ máy sinh viên hoặc thời gian sửa file không dùng làm bằng chứng nộp đúng hạn.
- Thi tập trung: BTC có thể bố trí máy nhận bài trong LAN, cấp biên nhận mã đội, hash và giờ nhận, rồi đồng bộ sau. Máy nhận bài cần đồng hồ được kiểm tra trước kỳ thi, lưu bền vững và có người phụ trách.
- Thi trực tuyến: nếu hệ thống của BTC gián đoạn, BTC thông báo gia hạn chung và lưu sự kiện; không tự chấp nhận bài trễ dựa trên khai báo local.
- Google Form có thể làm kênh đăng ký/nhận dự phòng nếu được công bố trước. Mọi bài dự phòng vẫn phải nhập kho bài chính và đối chiếu biên nhận trước khóa bài.

## 9. Công bố, khiếu nại và hành vi bị cấm

Điểm kỹ thuật trả riêng cho đội; kết quả chính thức chỉ công bố đồng thời vào thời điểm BTC đã thông báo. Không công khai source code, stderr chứa thông tin riêng hoặc replay làm lộ kết quả trước giờ công bố.

Đề xuất thời hạn khiếu nại: 24 giờ sau công bố kết quả tạm thời. Khiếu nại cần mã đội, mã ván, diễn giải và bằng chứng. BTC quyết định dựa trên bản đã khóa, log, replay và quy định; lưu quyết định thành biên bản. Kết quả cuối cùng được công bố sau xử lý khiếu nại.

Cấm đọc dữ liệu ngoài giao thức, tấn công sandbox/hạ tầng, giả mạo danh tính, sửa bài sau hạn, thông đồng làm sai kết quả. Nghi ngờ sao chép phải được người phụ trách xem xét có bằng chứng; không tự loại đội chỉ từ điểm tương đồng mã nguồn.

Huy chương, tiền thưởng, điểm rèn luyện hoặc điểm học phần chỉ được áp dụng khi đơn vị có thẩm quyền phê duyệt; website không tự cam kết các quyền lợi này.

Xem tiếp: [Chấm điểm và xếp hạng](CHAM_DIEM_XEP_HANG.md), [Host và vận hành](HOST_DEMO_VA_VAN_HANH.md).
