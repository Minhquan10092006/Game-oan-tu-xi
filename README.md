# Demo Oẳn Tù Tì — 2 chương trình Python

Đây là demo tối giản: người dùng nộp hai file Python, server lần lượt gọi Player 1 và Player 2 bằng JSON qua stdin, game engine xác nhận nước đi, rồi giao diện phát lại toàn bộ trận.

Không có đăng nhập, nộp bài, ELO, xếp hạng, phòng online hoặc Judge0 trong các route public của demo.

## Chạy local

Yêu cầu Python 3.10+.

```bash
cd /home/nqghuy/Documents/Game-oan-tu-xi
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Mở http://127.0.0.1:8000/. Chọn `bots/student1_bot.py` cho Player 1 và `bots/student2_bot.py` cho Player 2, chọn bàn cờ, rồi nhấn **Bắt đầu trận**. Khi server chạy xong, nhấn Play hoặc Step để xem replay.

## Giao thức chương trình Player

Mỗi lượt chương trình nhận đúng một JSON object ở stdin và in đúng một JSON object ở stdout. Không ghi log ra stdout.

```json
{
  "move": {
    "piece_id": "P1-P1",
    "from": [1, 3],
    "to": [2, 4]
  },
  "userdata": null
}
```

Server gửi trường `legal_moves`; code Player phải chọn một phần tử trong danh sách đó. Mọi tọa độ là `[row, col]`, bắt đầu từ 1. Bot crash, timeout, JSON sai hoặc chọn nước không hợp lệ sẽ bị xử thua.

Test nhanh:

```bash
python manage.py test matches.tests_battlecode
python bots/student1_bot.py < bots/sample_input.json
```
