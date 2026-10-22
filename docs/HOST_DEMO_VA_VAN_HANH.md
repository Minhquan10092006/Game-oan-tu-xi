# HOST DEMO VÀ PHƯƠNG ÁN VẬN HÀNH TIẾT KIỆM

Ngày đối chiếu: 19/10/2026. Mục tiêu: demo đủ thuyết phục để trường xem xét; chỉ thuê tài nguyên có phí sau khi được cấp kinh phí. Tài liệu này không khởi tạo hay mua dịch vụ.

## 1. Quyết định ở giai đoạn hiện tại

**Giữ Render đang có.** Demo đăng nhập, nhận bài, duyệt bài và replay hai chiến thuật mẫu do dự án cung cấp. Không chạy code upload trong tiến trình web. Bot sinh viên được chạy bằng công cụ local trên máy chấm riêng khi đã thiết lập sandbox.

Không cần chuyển toàn bộ sang Cloudflare hoặc dựng cụm AWS chỉ để trình diễn. Nhà trường có thể đánh giá luật, giao diện và quy trình bằng demo hiện tại. Docker trên máy cá nhân phục vụ diễn tập; trước khi chạy mã không tin cậy phải dùng máy/VM chuyên dụng không có dữ liệu cá nhân, secret web hoặc quyền cloud.

Render Free có thể ngủ sau 15 phút không có traffic, dữ liệu filesystem tạm không bền vững và PostgreSQL Free hết hạn sau 30 ngày. Chỉ dùng dữ liệu thử, có bản xuất trước buổi trình bày; nếu DB hiện tại có dữ liệu cần giữ, sao lưu trước khi hết hạn. Không dùng kỹ thuật ping liên tục làm bảo đảm sẵn sàng. [Render Free](https://render.com/docs/free)

## 2. Các lựa chọn sau khi trường duyệt

| Lựa chọn | Chi phí/phạm vi | Khi phù hợp |
|---|---|---|
| Máy trường cho chấm + web trả phí | Tận dụng CPU máy trường; trả phí web, DB và backup | Ưu tiên nếu có máy Linux/VM và cán bộ phụ trách |
| Render trả phí cho web/DB + máy chấm riêng | Ít công vận hành web; tiền máy chấm tính riêng | Khi không bắt buộc đặt web trên AWS |
| AWS Lightsail cho web/DB + máy trường cho chấm | Giá máy cố định dễ lập dự toán; phải tự quản DB, backup, vá OS | Khi trường yêu cầu AWS và có người vận hành |
| AWS cho cả web và chấm, tách hai máy | Đắt hơn nhưng tách rủi ro và chủ động tài nguyên | Khi trường không có máy chấm phù hợp |

Tham chiếu AWS Lightsail Linux có IPv4: máy 2 GiB RAM là **12 USD/tháng**, máy 4 GiB RAM là **24 USD/tháng** trong bảng giá đã kiểm tra. Hai máy 4 GiB có tiền máy cơ sở 48 USD/tháng nếu giữ cả tháng. Chưa gồm snapshot, thuế, lưu trữ/traffic vượt mức và dịch vụ phụ. Khu vực có thể khác allowance hoặc lựa chọn gói. [Bảng gói chính thức AWS](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html)

Render từng nêu ví dụ web always-on và PostgreSQL nhỏ khoảng **13 USD/tháng** trong bài hướng dẫn, nhưng đó là cấu hình tham chiếu theo thời điểm, không phải báo giá cam kết cho giải này. Phải xác nhận giá dịch vụ, storage và workspace trên dashboard khi trường duyệt. [Giải thích chi phí Render](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses), [bảng giá](https://render.com/pricing)

**Đề xuất ưu tiên:** máy chấm của trường + web/DB trả phí nhỏ. Nếu bắt buộc AWS, thử web/DB trên một Lightsail 4 GiB trước và đo tải; không tự kết luận gói 2 GiB đủ cho kỳ thi. Nếu trường không có người quản trị DB, chi phí DB managed cao hơn có thể hợp lý hơn tổng công vận hành.

Không chọn gói chỉ theo số RAM. Máy có CPU burst cần đo khi chạy liên tục nhiều giờ; không dùng tốc độ vài phút đầu làm năng lực máy chấm. Không cần Kubernetes, nhiều dịch vụ managed hoặc autoscaling ở V1 chỉ có một worker tuần tự.

## 3. Tiêu chí “ngon, bổ, rẻ” có thể kiểm tra

- **Đúng:** cùng luật, cùng môi trường; điểm chỉ tính từ replay/kết quả hợp lệ; không tính lỗi hạ tầng là thua.
- **Đủ:** diễn tập ít nhất gấp hai mức gửi bài đồng thời dự kiến; kiểm tra giới hạn request, DB, bộ nhớ và lỗi. Đây là mục tiêu kiểm thử, chưa phải số đo đã đạt.
- **Dễ quản:** chỉ có web/DB và máy chấm tách biệt, mỗi phần có người phụ trách; lưu tài khoản thuộc trường, bật MFA cho quản trị.
- **Dễ khôi phục:** backup có kiểm tra phục hồi, bài khóa và replay có bản sao ngoài máy; lưu lại mỗi ván để mất worker không phải chạy lại cả giải.
- **Tiết kiệm:** chỉ mở máy chấm cloud trong thời gian cần; kiểm tra quy tắc tính phí trước khi dừng/xóa máy. Snapshot, IP, disk và DB có thể vẫn phát sinh phí. Không dựa vào credit miễn phí để hứa ngân sách lâu dài.
- **Dự toán đủ:** tiền máy + DB + backup + storage + traffic + domain + thuế + thời gian vận hành. Dành khoảng 20% dự phòng như một giả định lập ngân sách, không phải giá nhà cung cấp.

Trước khi mua, cần có số đội, số ván, giờ phải hoàn tất, mức gửi bài đồng thời, số người xem và người trực sự cố. Đo `thời gian thực tế/ván × số ván / số worker an toàn`, cộng chuẩn bị sandbox và dự phòng chạy lại.

Cloudflare có thể bổ sung DNS/cache/bảo vệ web khi thật sự cần. Không cache response đăng nhập, bài nộp, replay riêng hoặc kết quả chưa công bố. Việc dùng Cloudflare không thay thế cách ly bot. Sandbox Cloudflare cũng yêu cầu tách đơn vị tin cậy và quyền truy cập. [Mô hình bảo mật](https://developers.cloudflare.com/sandbox/concepts/security/)

## 4. Ranh giới triển khai V1

Web Django → DB nhận bài. BTC xuất các bài đã chọn → thư mục giải khóa → worker local chạy Docker → lưu replay/kết quả → lệnh xuất bảng xếp hạng → BTC công bố.

Thư mục giải đóng vai trò hàng đợi bền vững đơn giản: `manifest.json` liệt kê ván phải chạy, `results/` lưu ván hoàn tất, `attempts/` giữ lần lỗi. Một bộ điều phối tại một thời điểm. Không có Celery/SQS hay chạy song song phân tán trong phiên bản này; tránh thuê hạ tầng trước nhu cầu.

Khi cần chấm liên tục quy mô lớn mới bổ sung queue dịch vụ, worker lease/heartbeat, ghi kết quả idempotent trong DB và object storage. Channels hiện dùng bộ nhớ, vì thế chưa được tăng nhiều web process cho phòng realtime; phải chuyển channel layer và trạng thái phòng sang cơ chế chia sẻ bền vững trước khi scale.

Docker runner hiện là lớp cách ly cơ bản, dùng kernel chung với máy chấm. Không coi Docker là bảo đảm tuyệt đối trước mã chủ ý tấn công. Giải chính thức cần máy/VM riêng, OS/runtime được vá, hạn chế quyền host, rà soát bảo mật và thử các tình huống tài nguyên. Không gắn Docker socket vào web, không gắn cả thư mục bài thi hay secret vào container bot.

## 5. Checklist trước giải chính thức

1. Thầy/BTC phê duyệt thể lệ, deadline, cách khóa bài, tie-break và khiếu nại.
2. Kiểm tra đúng image Python, đúng hash source/engine và phần cứng; thử bot mẫu cùng bộ thử đã công bố.
3. Thử bot lặp vô hạn, in quá nhiều, dùng nhiều RAM, tạo tiến trình và truy cập mạng trong môi trường chuyên dụng; không thử trên máy có dữ liệu quan trọng.
4. Thử ngắt worker giữa ván: ván chưa có kết quả được chạy lại, ván xong không tính trùng.
5. Thử restore DB, manifest, mã nguồn và replay từ backup sang máy khác.
6. Diễn tập nhận bài mất kết nối, biên nhận/hash, xử lý deadline và máy nhận LAN nếu sử dụng.
7. Kiểm tra tài khoản admin, quyền xem bài/replay, CSRF, hạn mức nộp và log lỗi lưu dữ liệu.
8. Lập danh sách người trực, cách thông báo tạm dừng, quy trình hủy/chạy lại kết quả và công bố đồng thời.

Không chuyển deployment sát ngày thi. Chạy giải thử trước, giữ một bản release ổn định và một bản backup có thể khôi phục. Những bước cần hạ tầng thật ở trên chưa được xem là hoàn tất chỉ vì unit test chạy thành công.
