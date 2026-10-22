# Đặc tả hệ thống Battlecode Oẳn Tù Tì

> **Tài liệu lịch sử.** Từ bản k71-v1.0, luật và phương án triển khai hiện hành nằm trong [docs/LUAT_THI_DAU_K71.md](docs/LUAT_THI_DAU_K71.md), [docs/CHAM_DIEM_XEP_HANG.md](docs/CHAM_DIEM_XEP_HANG.md) và [docs/HUONG_DAN_CHAY_GIAI.md](docs/HUONG_DAN_CHAY_GIAI.md). Giải chỉ nhận Python; demo web dùng bot mẫu, code nộp chạy trên máy chấm Docker riêng.

> Tài liệu đầu vào cho AI coding agent triển khai demo. Ưu tiên một bản chạy được end-to-end trước, sau đó mới mở rộng. Đặc tả này thay thế các phần README cũ liên quan đến AI Judge/Judge0, chấm điểm bài nộp, ELO, tài khoản, phòng 8 người, spectator và database. **Không tích hợp AI Judge/Judge0**; chỉ xây dựng nền tảng để hai bot tự động đấu với nhau và người dùng xem lại diễn biến.

## 1. Mục tiêu và phạm vi demo

Xây dựng website để hai sinh viên nộp chương trình điều khiển quân cờ bằng **Python hoặc C++**, chọn hai bot làm Player 1 và Player 2, khởi chạy trận đấu tự động và quan sát bàn cờ cập nhật theo từng nước đi. Đây là game Battlecode: sinh viên viết chiến thuật cho bot, không điều khiển thủ công.

### Có trong demo

- Giao diện tải lên hai file bot, nhập tên sinh viên/bot và chọn cấu hình bàn cờ.
- Hỗ trợ file `.py` và `.cpp`. Bot C++ được biên dịch trước trận đấu; không biên dịch lại ở mỗi nước.
- Engine luật chơi độc lập với giao diện, là nguồn chân lý duy nhất để sinh nước hợp lệ, cập nhật trạng thái, bắt quân và xác định kết quả.
- Runner gọi bot theo giao thức JSON qua stdin/stdout, giới hạn thời gian và xử lý lỗi.
- Giao diện bàn cờ, quân Kéo/Búa/Bao, ô chướng ngại vật, lượt hiện tại, số quân còn lại, lịch sử nước đi và lý do kết thúc.
- Điều khiển trình diễn: phát/tạm dừng, đi từng nước, tốc độ (ví dụ 0.25x, 0.5x, 1x, 2x), mặc định cách nhau 1 giây mỗi nước.
- Kết thúc trận và xem lại từ đầu.
- Các preset: bàn vuông 9×9 mặc định, bàn chữ nhật, bàn chữ thập và bàn có chướng ngại vật.

### Chưa làm trong bản demo

Không cần đăng ký/đăng nhập, ELO, bảng xếp hạng, đấu online, phòng nhiều người, hệ thống nộp bài/chấm điểm theo rubric, AI Judge/Judge0, dịch vụ bên ngoài hoặc database phức tạp. Có thể lưu lịch sử trận thành JSON để tải/xem lại, nhưng không bắt buộc phải có database.

## 2. Công nghệ và nguyên tắc triển khai

- Nếu repository hiện tại đã có Django và giao diện bàn cờ, **kiểm tra và tái sử dụng phần đang dùng được**; không viết lại toàn bộ chỉ để đổi framework. Nếu chưa có backend phù hợp, có thể dùng FastAPI hoặc Django với HTML/CSS/JavaScript.
- Tách module tối thiểu: `game_engine`, `bot_runner`, `match_manager`, API/backend và frontend.
- Engine không phụ thuộc framework web. Viết unit test cho luật di chuyển, bắt quân, thắng/thua/hòa và cấu hình bàn.
- Giao diện không tự quyết định luật. Mọi nước đi đều do backend xác nhận.
- Kết quả trận phải tái lập được với cùng bot, trạng thái, cấu hình và phiên bản giao thức; hai bot mẫu nên là chiến lược xác định, không phụ thuộc thư viện bên ngoài.
- Các ví dụ mã trong tài liệu sử dụng tọa độ `[row, col]`, đánh số từ **1** giống nhãn hàng/cột trên giao diện.

## 3. Luật chơi mặc định

### 3.1 Bàn cờ và quân cờ

- Bàn mặc định 9 hàng × 9 cột.
- Mỗi bên bắt đầu với 9 quân: 3 Búa (`rock`), 3 Bao (`paper`), 3 Kéo (`scissors`).
- Player 1 đi trước.
- Player 1 có đích `(9,9)`; Player 2 có đích `(1,1)`. Đây là ô ở góc đối diện, không phải ô xuất phát.
- Cách bố trí xuất phát mặc định (mỗi ký hiệu là một quân):

  ```text
  Player 1                 Player 2
  S R P                    S P R
  P S R                    R S P
  R P S                    P R S
  ```

  Player 1 đặt cụm 3×3 ở hàng 1–3, cột 1–3. Player 2 đặt cụm 3×3 ở hàng 7–9, cột 7–9. `R=rock`, `P=paper`, `S=scissors`. Hai cụm này phải được cấu hình rõ trong code chứ không suy ra từ UI.

### 3.2 Quan hệ khắc chế

- Búa (`rock`) thắng Kéo (`scissors`).
- Kéo (`scissors`) thắng Bao (`paper`).
- Bao (`paper`) thắng Búa (`rock`).
- Hai quân cùng loại không bắt được nhau.

### 3.3 Di chuyển và bắt quân

- Mỗi nước đi một quân sang một ô kề theo 8 hướng, như quân Vua trong cờ vua: `max(abs(delta_row), abs(delta_col)) == 1`.
- Không được đi ra ngoài bàn, vào ô không chơi được, vào ô chướng ngại vật hoặc ô đang có quân cùng phe.
- Ô trống: được đi vào.
- Ô có quân đối phương: chỉ được đi vào nếu quân đang đi khắc chế quân ở ô đích. Quân bị bắt bị loại khỏi bàn; quân tấn công chiếm ô đó.
- Nếu quân ở ô đích và thực hiện nước bắt quân hợp lệ để vào đích, trận thắng ngay sau nước đi đó.
- Không có nước đi nhảy qua quân/ô khác. Vì mỗi nước chỉ đi một ô nên chỉ cần kiểm tra ô đích.
- Không có nước “pass”. Nếu còn quân nhưng không có nước hợp lệ, người chơi hiện tại thua do bị khóa nước.
- Engine tạo `legal_moves`; bot chỉ chọn trong danh sách đó. Không tin nước đi do bot tự khai là hợp lệ.

### 3.4 Điều kiện kết thúc

Kiểm tra theo thứ tự ngay sau mỗi nước đi:

1. **Thắng do tới đích:** bất kỳ quân nào của bên vừa đi đến ô đích đối phương.
2. **Thắng do loại quân:** bên vừa đi bắt hết quân đối phương.
3. **Hết nước đi:** nếu đến lượt một bên mà không có nước hợp lệ, bên đó thua.
4. **Hòa do lặp trạng thái:** cùng một trạng thái bàn cờ (vị trí, loại và chủ sở hữu tất cả quân, cùng bên đến lượt) xuất hiện 3 lần.
5. **Hòa do giới hạn nước:** chạm `max_plies=300` (một ply là một nước của một người chơi).
6. **Bot bị xử thua:** timeout, crash, output không phải JSON hợp lệ, output không đúng schema hoặc chọn nước không nằm trong `legal_moves`. UI phải ghi rõ lý do, ví dụ “Player 2 thua do timeout”.

Kết quả nên được biểu diễn bằng cấu trúc nhất quán: `status` (`finished`), `winner` (`P1`, `P2` hoặc `null`), `result` (`win`, `draw`, `forfeit`) và `reason` (mã máy đọc được + thông báo thân thiện). Khi bot bị xử thua, đối thủ là người thắng; lỗi khởi tạo/biên dịch bot cũng tính là bot đó bị xử thua. Nếu cả hai bot đều không chạy được trước khi trận bắt đầu, hiển thị lỗi tạo trận thay vì tự gán người thắng.

## 4. Cấu hình bàn cờ có thể mở rộng

Thiết kế engine theo cấu hình dữ liệu, không hard-code luật vào từng hình bàn.

```json
{
  "rows": 9,
  "cols": 9,
  "shape": "rectangle",
  "playable_cells": null,
  "blocked_cells": [[5, 5]],
  "goals": {"P1": [9, 9], "P2": [1, 1]},
  "initial_pieces": []
}
```

- `rows`, `cols`: kích thước bao ngoài.
- `playable_cells`: `null` nghĩa là toàn bộ ô trong hình chữ nhật đều chơi được, trừ `blocked_cells`. Nếu là danh sách tọa độ thì chỉ các ô trong danh sách đó chơi được; hỗ trợ bàn hình chữ thập hoặc hình dạng tùy chỉnh.
- `blocked_cells`: các ô chướng ngại vật, luôn không thể đi vào. Không được trùng ô quân xuất phát hoặc ô đích.
- `goals`: đích của mỗi bên, phải là ô chơi được.
- `initial_pieces`: danh sách quân xuất phát gồm `id`, `owner`, `type`, `at`. Với preset bàn mới, cấu hình phải chỉ rõ vị trí và xác thực không trùng ô.
- `shape` chỉ là tên hiển thị/preset; kiểm tra khả năng di chuyển dựa trên `playable_cells` và `blocked_cells`.

Tạo ít nhất 4 preset:

1. `classic_9x9`: luật mặc định, không chướng ngại vật.
2. `rectangle_7x11`: bàn chữ nhật, cấu hình đích và đội hình riêng.
3. `cross_9x9`: chỉ một tập ô tạo hình chữ thập được chơi; đặt đích và đội hình trong tập ô đó.
4. `obstacles_9x9`: giống classic nhưng có một vài chướng ngại vật không chặn đường xuất phát/đích.

Với bàn chữ thập, không được chỉ kiểm tra biên hàng/cột: engine phải từ chối ô không có trong `playable_cells`. Khi tạo cấu hình, xác thực đội hình hợp lệ, hai đích hợp lệ và không có hai quân ở cùng ô.

**Phạm vi bản đầu:** bot chỉ cần hỗ trợ luật chung và nhận `board` + `legal_moves` từ engine. Không bắt buộc bot tự tính đường đi cho mọi hình bàn.

## 5. Giao thức bot (Python/C++)

### 5.1 Quy tắc giao tiếp

- Mỗi lượt, runner khởi chạy bot và gửi **một JSON object duy nhất** vào stdin.
- Bot in **một JSON object duy nhất** ra stdout rồi kết thúc. Không in log/debug ra stdout; nếu cần debug thì ghi stderr.
- UTF-8, không cần network. Không dựa vào thứ tự key trong JSON.
- Runner kiểm tra output và xác minh nước đi với `legal_moves` trước khi cập nhật bàn.
- Python: `python bot.py`; C++: biên dịch một lần bằng compiler có sẵn (ví dụ `g++`) rồi chạy executable.
- Mỗi bot nhận toàn bộ thông tin nhìn thấy của bàn, gồm tất cả quân hai bên; không có thông tin ẩn.
- Vì tiến trình được khởi chạy lại mỗi lượt, bot có thể lưu trạng thái nhỏ trong `userdata`, runner trả lại ở lượt sau của cùng bot. Không dùng file ngoài để giao tiếp giữa lượt.

### 5.2 Input JSON

Ví dụ rút gọn (danh sách `pieces` và `legal_moves` trong thực tế được engine tạo đầy đủ):

```json
{
  "protocol_version": "1.0",
  "match_id": "demo-001",
  "turn": 1,
  "ply": 0,
  "current_player": "P1",
  "board": {
    "rows": 9,
    "cols": 9,
    "shape": "rectangle",
    "playable_cells": null,
    "blocked_cells": [[5, 5]],
    "goals": {"P1": [9, 9], "P2": [1, 1]}
  },
  "players": {
    "P1": {
      "goal": [9, 9],
      "pieces": [
        {"id": "P1-S1", "type": "scissors", "at": [1, 1]},
        {"id": "P1-R1", "type": "rock", "at": [1, 2]}
      ]
    },
    "P2": {
      "goal": [1, 1],
      "pieces": [
        {"id": "P2-P1", "type": "paper", "at": [9, 8]}
      ]
    }
  },
  "legal_moves": [
    {
      "piece_id": "P1-S1",
      "from": [1, 1],
      "to": [2, 1],
      "capture_piece_id": null,
      "capture": false,
      "wins_immediately": false
    }
  ],
  "userdata": null
}
```

Các trường có ý nghĩa:

- `turn`: số lượt của người chơi hiện tại, bắt đầu từ 1; `ply`: tổng số nước đã thực hiện, bắt đầu từ 0.
- `players.*.pieces`: chỉ các quân còn sống; `at` theo `[row, col]`, đếm từ 1.
- `legal_moves`: tất cả nước hợp lệ do engine sinh ra. Các bot mẫu nên chọn một phần tử từ danh sách này, không tự dựng nước đi.
- `capture_piece_id`: ID quân đối thủ sẽ bị bắt, hoặc `null`.
- `wins_immediately`: engine đánh dấu nếu nước đó kết thúc trận theo điều kiện tới đích/loại quân.
- `userdata`: dữ liệu JSON tùy chọn do chính bot trả về ở lượt trước; giới hạn khuyến nghị 4 KB.

Input được cấp qua stdin. Không giả định có newline ở cuối input.

### 5.3 Output JSON

Nếu có nước hợp lệ:

```json
{
  "move": {
    "piece_id": "P1-S1",
    "from": [1, 1],
    "to": [2, 1]
  },
  "userdata": null
}
```

`piece_id`, `from`, `to` phải khớp với đúng một phần tử trong `legal_moves`. `userdata` có thể bỏ qua hoặc trả về JSON bất kỳ nhỏ gọn. Khi `legal_moves` rỗng, engine phải kết thúc trận do hết nước đi và không cần gọi bot; nếu vẫn gọi để debug, output `{"move": null}` được chấp nhận nhưng không làm thay đổi kết quả.

Ví dụ Python tối giản:

```python
import json, sys
state = json.load(sys.stdin)
if not state["legal_moves"]:
    print(json.dumps({"move": None}))
else:
    m = state["legal_moves"][0]
    print(json.dumps({"move": {"piece_id": m["piece_id"], "from": m["from"], "to": m["to"]}, "userdata": state.get("userdata")}))
```

### 5.4 Thông báo lỗi

- Output rỗng, JSON sai, thiếu `move`, sai kiểu dữ liệu hoặc nước đi không hợp lệ: xử thua.
- Timeout hoặc process bị crash: xử thua; lưu mã lỗi và stderr đã cắt ngắn để người dùng xem.
- Chỉ đọc một JSON input và chỉ chấp nhận JSON output. Không chấp nhận output kiểu văn bản tự do.
- Giới hạn khởi đầu đề xuất: 2 giây cho mỗi nước, 256 MB RAM cho mỗi tiến trình, file upload tối đa 256 KB, giới hạn stdout/stderr và tổng thời gian trận. Cho phép cấu hình các giới hạn này ở server.

## 6. Chạy mã sinh viên an toàn (rất quan trọng)

Mã do sinh viên tải lên là mã không đáng tin cậy.

- **Không chạy code upload trực tiếp trong process web/backend.**
- Thực thi trong worker/sandbox tách biệt, không root, filesystem tạm, không mount secrets, không network, giới hạn CPU/RAM/PID/thời gian, kill toàn bộ process group khi timeout.
- Biên dịch C++ trong sandbox với compiler đã cài; không cho bot tự biên dịch hoặc tải gói trong lúc thi đấu.
- Xóa thư mục tạm sau trận; kiểm soát kích thước file, tên file và dung lượng output.
- Demo chạy trên máy cá nhân vẫn cần coi bot là mã độc tiềm tàng. Có thể dùng container/namespace có giới hạn; Docker đơn lẻ không nên được coi là ranh giới bảo mật hoàn hảo cho triển khai công khai.
- Không dùng Judge0 hay dịch vụ thực thi code bên ngoài trong bản này.

## 7. Giao diện người dùng

### 7.1 Màn hình tạo trận

- Hai khu vực Player 1 và Player 2: tên sinh viên/bot, nút chọn file, hiện tên file và ngôn ngữ được nhận diện.
- Chỉ chấp nhận `.py` hoặc `.cpp`; nếu chưa chọn đủ hai file thì không cho bắt đầu.
- Chọn preset bàn cờ; có thể hiện preview nhỏ của preset và mô tả kích thước.
- Cấu hình nâng cao: số nước tối đa, thời gian tối đa mỗi nước, delay mặc định 1000 ms.
- Nút “Bắt đầu trận”. Hiện trạng thái biên dịch/khởi tạo, không treo UI trong khi backend chạy.

### 7.2 Màn hình trận đấu

- Bàn cờ responsive, nhãn hàng/cột nhất quán với tọa độ JSON; ô chướng ngại vật có hình/texture riêng.
- Hiện quân theo loại và màu người chơi, lượt hiện tại, đích, số quân còn lại.
- Nước vừa đi được tô sáng; nước bắt quân thể hiện quân bị loại; thêm thông báo cho tới đích/kết thúc.
- Bảng lịch sử: số ply, bên đi, loại quân, tọa độ đi, quân bị bắt nếu có. Chọn một bản ghi để nhảy tới trạng thái tương ứng.
- Nút Play/Pause, Step (đúng một nước), Restart/Replay, tốc độ phát và thanh tiến trình. Mặc định 1 giây/nước.
- Khi trận kết thúc, hiện người thắng/hòa, lý do rõ ràng và nút “Xem lại”/“Trận mới”.

### 7.3 Trải nghiệm và khả năng truy cập

- Không dùng emoji làm phương tiện duy nhất để phân biệt quân; phải có màu, ký hiệu và chú giải.
- Trạng thái lỗi cần dễ hiểu, không chỉ hiện stack trace.
- Không mất lịch sử trận khi Play/Pause/Step. Tốc độ phát chỉ ảnh hưởng animation, không thay đổi kết quả hoặc luật.

## 8. Kiến trúc backend/API đề xuất

Có thể đổi tên route để phù hợp repository hiện tại, nhưng chức năng phải tương đương.

- `POST /api/matches`: nhận multipart form gồm file Player 1, file Player 2, tên bot và cấu hình; xác thực cấu hình, tạo match ID và bắt đầu worker. Trả `match_id`.
- `GET /api/matches/{match_id}`: trả metadata, trạng thái, kết quả nếu xong và số ply hiện tại.
- `GET /api/matches/{match_id}/state`: trả snapshot bàn cờ để khôi phục UI.
- `GET /api/matches/{match_id}/events`: SSE hoặc WebSocket phát sự kiện `started`, `move`, `finished`, `error`. Chọn một phương thức cho demo, tránh làm cả hai khi chưa cần.
- `POST /api/matches/{match_id}/control`: điều khiển `pause`, `resume`, `step`, `stop`, hoặc có thể thực hiện Play/Pause/Step hoàn toàn ở frontend khi toàn bộ replay đã được tạo xong.
- `GET /api/boards`: trả các preset bàn cờ được hỗ trợ.

Một `move` event nên có `ply`, `player`, `piece_id`, `piece_type`, `from`, `to`, `captured_piece`, `state_after`, `message`. `finished` event gồm `winner`, `result`, `reason`, `final_state`.

### Cách triển khai demo đơn giản

Chọn một trong hai cách và giữ nhất quán:

A. **Chạy trận rồi phát lại:** worker chạy trận trong giới hạn an toàn, lưu danh sách state/event; frontend phát từng event cách nhau 1 giây và hỗ trợ pause/step/replay. Dễ triển khai điều khiển animation.

B. **Chạy trận trực tiếp:** backend chạy một ply, chờ theo nhịp, rồi gửi event qua SSE/WebSocket; cần cơ chế pause/resume/step rõ ràng.

Khuyến nghị bắt đầu với A để dễ làm demo, nhưng phải đảm bảo tổng thời gian bot và số ply vẫn bị giới hạn. Có thể hiển thị “Đang tính trận…” trong lúc chạy và phát lại ngay khi có kết quả. Nếu muốn thấy trận bắt đầu gần như tức thời, dùng B.

## 9. Data model tối thiểu

Không bắt buộc database. Trong RAM hoặc file JSON theo match ID cần có:

- `Match`: id, status, board_config, player metadata, created_at, result.
- `MatchEvent`: ply, player, move, capture, snapshot sau nước đi.
- `GameState`: current_player, pieces còn sống, ply, số lần lặp trạng thái, winner/result/reason.
- `BotRun`: player, language, exit code, elapsed_ms, timeout, stderr (đã giới hạn độ dài).

Nếu ghi file, chỉ lưu JSON do backend tạo; không dùng tên file upload nguyên gốc làm đường dẫn.

## 10. Bộ kiểm thử bắt buộc

### Engine

- Quân đi được đủ 8 hướng, chỉ 1 ô.
- Từ chối đi hai ô, ra ngoài bàn, vào ô không chơi được/chướng ngại vật, vào quân cùng phe.
- Búa bắt Kéo, Kéo bắt Bao, Bao bắt Búa; các trường hợp ngược chiều và cùng loại đều không bắt được.
- Không có nước nhảy qua ô khác.
- Tới đích thắng ngay; bắt hết quân thắng; hết nước thua; lặp trạng thái 3 lần hòa; giới hạn ply hòa.
- Bàn chữ nhật và bàn chữ thập tuân theo các ô chơi được.
- Phát hiện cấu hình sai: quân chồng ô, đích ngoài bàn, quân/đích trên obstacle, vị trí không chơi được.

### Runner/giao thức

- Bot Python hợp lệ và bot C++ hợp lệ chạy được.
- Xử lý JSON output sai, nước không hợp lệ, crash, timeout và output quá lớn.
- Bot không được thay đổi trạng thái trực tiếp; engine chỉ dùng nước hợp lệ đã xác minh.
- Không có legal moves thì engine kết thúc trước khi gọi bot.

### UI

- Tải lên đủ hai file, tạo trận, xem bàn và lịch sử.
- Play/Pause/Step/Replay và đổi tốc độ hoạt động.
- Hiển thị đúng lượt, quân bị bắt và kết quả.
- Không vỡ bố cục ở màn hình nhỏ.

## 11. Tiêu chí nghiệm thu demo

1. Người dùng mở website và thấy màn hình tạo trận.
2. Upload được hai bot Python mẫu và chọn preset classic 9×9.
3. Nhấn bắt đầu, hệ thống tự điều khiển cả hai bên cho đến khi có kết quả.
4. Bàn cờ cập nhật được theo từng nước, mặc định 1 giây/nước; có Pause, Step và Replay.
5. Lịch sử nước đi khớp hoàn toàn với state trên bàn.
6. Bot sai giao thức/timeout/đi sai bị xử thua rõ lý do, không làm sập server.
7. Có ít nhất một preset bàn chữ thập và một preset obstacle hoạt động ở engine, không chỉ là hình ảnh.
8. Không còn phụ thuộc Judge0, không còn tính năng AI Judge/chấm điểm submission/ELO trong luồng demo.
9. README hướng dẫn cài đặt/chạy và giao thức bot; hai file mẫu ở thư mục dễ tìm.

## 12. Test nhanh giao thức bot mẫu

Thư mục bàn giao có `sample_input.json`, một trạng thái đầu vào mẫu để kiểm tra giao thức. Từ thư mục chứa các file, chạy:

```bash
python student1_bot.py < sample_input.json
python student2_bot.py < sample_input.json
```

Mỗi lệnh phải in đúng một dòng JSON có `move.piece_id`, `move.from` và `move.to`; nước trả về phải trùng một phần tử trong `legal_moves`. Đây chỉ là kiểm tra giao thức cho một nước, chưa phải engine hoàn chỉnh để chạy cả trận.

## 13. Kế hoạch triển khai cho AI coding agent

1. Khảo sát repository và xác định phần UI/engine hiện có có thể tái sử dụng.
2. Viết/chuẩn hóa `GameState`, cấu hình bàn và unit test engine trước.
3. Cài giao thức JSON + runner cho Python; sau đó hỗ trợ C++ compile-once/run-many.
4. Xây dựng match manager lưu snapshot/event, xử lý timeout/forfeit và điều kiện kết thúc.
5. Tích hợp UI upload hai bot và cấu hình bàn.
6. Xây dựng replay viewer với Play/Pause/Step/tốc độ 1 giây/nước.
7. Chạy kiểm thử engine, runner và luồng end-to-end bằng `student1_bot.py` và `student2_bot.py`.
8. Dọn README/config cũ: loại bỏ hướng dẫn AI Judge/Judge0, rubric chấm bài, ELO, đăng nhập và multiplayer nếu không còn dùng. Không xóa code cũ một cách mù quáng; kiểm tra import/route trước.

## 14. Quy ước tên và hiển thị

- `rock` = Búa, `paper` = Bao, `scissors` = Kéo.
- `P1`, `P2` là ID cố định trong một trận.
- ID quân phải duy nhất, ví dụ `P1-R1`, `P1-P1`, `P1-S1`.
- Tọa độ trong API dùng `[row, col]` bắt đầu từ 1; không dùng chỉ số array 0-based ra ngoài engine.
- Mọi quyết định luật/di chuyển/thắng thua phải ở game engine; frontend chỉ vẽ và điều khiển xem lại.
