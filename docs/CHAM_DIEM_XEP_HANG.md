# CHẤM ĐIỂM VÀ XẾP HẠNG — K71 V1

Đi kèm [thể lệ k71-v1.0](LUAT_THI_DAU_K71.md). Đây là phương án đề xuất trình trường.

## 1. Kiểm tra đầu vào: đạt hoặc cần sửa

Không dùng điểm phong cách code để quyết định thứ hạng thi đấu. BTC kiểm tra:

| Hạng mục | Điều kiện |
|---|---|
| Danh tính | Đội và thành viên hợp lệ, không đăng ký trùng trái quy định |
| File | Python UTF-8, tối đa 64 KiB, chạy được bằng image Python của giải |
| Giao thức | Đọc input và trả JSON đúng; không vượt giới hạn userdata/output |
| Luật | Chọn nước hợp lệ trên các tình huống công khai |
| Tài nguyên | Không vượt giới hạn khi chạy bộ thử công khai |

Bộ thử công khai nên có: bàn khởi đầu, nước bắt quân, bắt quân cuối của một loại, đến đích, bị quân cùng loại chặn, không còn nước đi, lặp trạng thái và gần hết 300 nước. BTC kiểm tra tình huống không còn nước đi ở engine, không gọi bot khi không có lựa chọn.

Đạt bộ thử là điều kiện nhận bài chính thức, không phải bảo đảm bot sẽ không lỗi ở mọi trận. Sinh viên được tải bộ thử và bot mẫu về local trước kỳ thi. Không có điểm thưởng bí mật vì dùng AI, thư viện hay thuật toán cụ thể.

## 2. Điểm mỗi ván

| Kết quả | Đội thắng | Đội thua |
|---|---:|---:|
| Thắng theo luật | 3 | 0 |
| Đối thủ bị xử thua vì lỗi bot | 3 | 0 |
| Hòa | 1 cho mỗi đội | 1 cho mỗi đội |
| Lỗi hạ tầng / đang chờ xử lý | Chưa có điểm | Chưa có điểm |

Điểm đội = `3 × số ván thắng + số ván hòa`. Không có điểm âm, điểm theo quân bắt được hoặc thưởng thắng nhanh. Lỗi hạ tầng không được tính hòa.

Một cặp đối đầu gồm hai ván: A làm P1/B làm P2, sau đó B làm P1/A làm P2. Hai ván có cùng cấu hình và hai bản bot đã khóa. Cộng điểm từng ván; không có điểm thưởng thắng cả cặp.

Ví dụ A thắng một ván, hòa một ván với B: A được 4 điểm, B được 1 điểm. Hai đội mỗi bên thắng một ván: mỗi đội 3 điểm.

## 3. Thể thức đề xuất

- **2–16 đội:** vòng tròn hai lượt toàn bộ; N đội có `N × (N−1)` ván, mỗi đội `2 × (N−1)` ván.
- **17–128 đội:** chia `ceil(N/16)` bảng, số đội chênh lệch không quá một. Bốc thăm bằng seed được công bố và lưu biên bản trước chấm. Mỗi bảng vòng tròn hai lượt; lấy hai đội đầu bảng vào chung kết vòng tròn hai lượt.
- Điểm vòng bảng không chuyển sang vòng chung kết. Không so tổng điểm giữa các bảng khác kích thước.
- Giữ nguyên bài đã khóa trong cả vòng bảng và chung kết, trừ khi điều lệ ban đầu công bố một đợt nộp mới cho tất cả đội vào chung kết.
- Hơn 128 đội: BTC phải xây dựng thể thức và ngân sách mới trước mở đăng ký; công cụ hiện tại không tự xếp Swiss.

Ví dụ 64 đội: 4 bảng × 16 đội → 960 ván; chung kết 8 đội → 56 ván; tổng 1.016 ván. Với mỗi ván trung bình 30 giây, một worker tuần tự mất khoảng 8,47 giờ, chưa gồm khởi tạo sandbox và chạy lại. Đây là minh họa tính dung lượng, không phải benchmark đã đo.

Trước giải phải đo thời gian P50/P95 và giới hạn xấu nhất. Ván tối đa 300 nước × 5 giây = 1.500 giây thực thi, chưa tính chuẩn bị container. Không chọn số đội hoặc giờ công bố theo thời gian của một trận mẫu duy nhất.

## 4. Xếp hạng và phá hòa

Xếp theo các tiêu chí giảm dần, lần lượt:

1. **Tổng điểm.**
2. **Điểm đối đầu trong nhóm đồng tổng điểm:** cộng điểm các ván gặp đội có cùng tổng điểm cuối vòng. Với từ ba đội trở lên dùng bảng phụ của cả nhóm, tính một lần; không chia nhóm rồi tính lại đệ quy.
3. **Sonneborn–Berger (SB):** mỗi ván thắng cộng tổng điểm cuối vòng của đối thủ; mỗi ván hòa cộng một nửa tổng điểm cuối vòng của đối thủ; thua cộng 0. Hai ván gặp cùng đối thủ được tính riêng.
4. **Số ván thắng**, bao gồm thắng do đối thủ lỗi bot.
5. Nếu vẫn bằng nhau: **đồng hạng**. Mã đội chỉ dùng để sắp xếp hiển thị ổn định, không tạo lợi thế thể thao.

Đồng hạng hiển thị kiểu 1, 2, 2, 4. Ví dụ thắng hai ván trước đội có 10 điểm và hòa một ván trước đội có 12 điểm: SB của ba ván đó là `10 + 10 + 12/2 = 26`.

Nếu đồng hạng ảnh hưởng suất đi tiếp hoặc giải thưởng cần phân biệt:

- Tổ chức vòng phụ giữa các đội đang đồng hạng, vòng tròn hai lượt, cùng bài và môi trường đã khóa. Điểm vòng phụ tách riêng.
- Áp dụng lại các tiêu chí trên cho vòng phụ. Tối đa hai vòng phụ; nếu vẫn bằng nhau, bốc thăm công khai giữa các đội còn hòa cho suất cần chọn, có biên bản và người chứng kiến.
- Chính sách này phải công bố trước giải. Nếu giải thưởng cho phép chia sẻ thì BTC có thể công bố đồng giải ngay từ điều lệ ban đầu.

## 5. Hoàn tất, công bố và sửa kết quả

Không xuất bảng cuối cùng khi còn ván chưa chấm, lỗi hạ tầng hoặc kết quả chưa xác minh. Bảng tạm phải ghi rõ số ván còn thiếu. Các đội có số ván khác nhau trong lúc chấm không được xem là thứ hạng cuối.

Mỗi ván có một mã duy nhất và một kết quả được chấp nhận. Retry không được cộng điểm lần hai. Khi cần hủy kết quả, BTC sao lưu bản cũ vào hồ sơ khiếu nại, ghi lý do/người quyết định rồi mới chạy lại; không xóa dấu vết.

Khi có đội rút trước khóa bài: bỏ khỏi danh sách, lập lịch lại trước chấm. Sau khóa bài, mặc định tiếp tục chạy bản đã khóa để lịch đối thủ cân bằng. Khi loại một đội do vi phạm, đề xuất hủy toàn bộ kết quả liên quan đội đó trong vòng hiện tại và tính lại cho tất cả; BTC phải lập biên bản và công bố số ván/đội còn lại. Công cụ không tự động quyết định kỷ luật hoặc bỏ đội.

## 6. Phạm vi đã có trong code

`python -m matches.tournament` hỗ trợ khóa bài, lịch vòng tròn hai lượt, chạy tuần tự bằng Docker, lưu replay, tiếp tục các ván chưa hoàn tất và xuất JSON xếp hạng với tiêu chí trên. Giải chia bảng dùng một thư mục cho mỗi bảng và một thư mục riêng cho chung kết. BTC lập danh sách bảng/đội đi tiếp theo biên bản; công cụ chưa tự bốc thăm hoặc xử lý vòng phụ.

Bảng ELO trên website hiện là chức năng luyện tập cũ; không dùng để trao giải K71. Kết quả demo không ghi vào điểm giải. File xuất xếp hạng local chỉ công bố khi BTC chủ động đưa lên kênh thông báo vào thời gian quy định.
