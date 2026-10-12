"""
ai_sample.py — AI mẫu cho Game Oẳn Tù Tì 2.0
===============================================

Cách sử dụng:
    python ai_sample.py < input.json

Giao thức:
- Nhận MỘT JSON object từ stdin.
- In ra MỘT JSON object lên stdout.
- Ghi log/debug vào stderr (KHÔNG phải stdout).

Input schema (do Django gửi):
{
    "board": [
        [{"player": 1, "type": "rock", "id": "p1-rock-0"} | null, ...],  // 9 hàng
        ...
    ],
    "current_player": 1,          // 1 hoặc 2 — AI của bạn
    "turn_number": 1,
    "legal_moves": [              // Danh sách nước đi hợp lệ đã tính sẵn
        {
            "from_row": 2, "from_col": 0,
            "to_row": 3, "to_col": 0,
            "is_capture": false,
            "captured_type": null
        },
        ...
    ],
    "goal": {"row": 8, "col": 8},         // Đích của AI (0-indexed)
    "opponent_goal": {"row": 0, "col": 0}, // Đích của đối thủ
    "game_over": false
}

Output schema (AI phải in):
{
    "move": {
        "from_row": 2,
        "from_col": 0,
        "to_row": 3,
        "to_col": 0
    }
}

Quan trọng:
- Chỉ chọn nước đi từ legal_moves. Nếu chọn nước đi không có trong danh sách
  hoặc sai tọa độ, Django sẽ từ chối và không tính thắng/thua cho bất kỳ bên nào.
- Nếu legal_moves rỗng (hết nước đi), in {"move": null} để báo không có nước.
- Không print bất kỳ thứ gì khác lên stdout (sẽ làm hỏng JSON parse).
- Debug dùng sys.stderr.write() hoặc print(..., file=sys.stderr).
"""

import sys
import json
import math


# =====================================================================
# HELPER FUNCTIONS
# =====================================================================

def distance_to_goal(from_row: int, from_col: int, goal: dict) -> float:
    """Tính khoảng cách Chebyshev (king distance) từ ô này đến đích."""
    return max(abs(from_row - goal['row']), abs(from_col - goal['col']))


def score_move(move: dict, current_player: int, goal: dict,
               board: list) -> float:
    """
    Hàm heuristic đánh giá nước đi:
    - Ưu tiên capture (ăn quân).
    - Ưu tiên tiến gần đích.
    - Tránh nước đi giật lùi xa đích.
    """
    score = 0.0

    # Ưu tiên capture
    if move.get('is_capture'):
        score += 100.0

    # Điểm tiếp cận đích: khoảng cách giảm = tốt
    dist_before = distance_to_goal(move['from_row'], move['from_col'], goal)
    dist_after = distance_to_goal(move['to_row'], move['to_col'], goal)
    score += (dist_before - dist_after) * 10.0

    # Bonus nếu đến đích ngay (thắng)
    if move['to_row'] == goal['row'] and move['to_col'] == goal['col']:
        score += 1000.0

    return score


# =====================================================================
# MAIN AI LOGIC
# =====================================================================

def choose_move(data: dict) -> dict | None:
    """
    Lựa chọn nước đi từ danh sách legal_moves.
    Chiến lược: greedy heuristic đơn giản.

    Bạn có thể thay thế hàm này bằng:
    - Minimax / Alpha-Beta pruning
    - Monte Carlo Tree Search
    - Học máy (neural network)
    - Bất kỳ chiến thuật nào khác
    """
    legal_moves = data.get('legal_moves', [])

    if not legal_moves:
        print(f"[AI] Không có nước đi hợp lệ.", file=sys.stderr)
        return None

    current_player = data['current_player']
    goal = data['goal']
    board = data['board']

    # Đánh giá và chọn nước đi tốt nhất
    best_move = max(
        legal_moves,
        key=lambda m: score_move(m, current_player, goal, board)
    )

    print(
        f"[AI] P{current_player} chọn: "
        f"({best_move['from_row']},{best_move['from_col']}) → "
        f"({best_move['to_row']},{best_move['to_col']}) "
        f"capture={best_move.get('is_capture', False)}",
        file=sys.stderr
    )

    return {
        'from_row': best_move['from_row'],
        'from_col': best_move['from_col'],
        'to_row': best_move['to_row'],
        'to_col': best_move['to_col'],
    }


def main():
    # Đọc toàn bộ stdin
    raw_input = sys.stdin.read()

    # Parse JSON input
    try:
        data = json.loads(raw_input)
    except json.JSONDecodeError as e:
        print(f"[AI ERROR] Không parse được input: {e}", file=sys.stderr)
        # Vẫn phải in JSON hợp lệ ra stdout
        print(json.dumps({"move": None}))
        return

    # Kiểm tra game đã kết thúc chưa
    if data.get('game_over', False):
        print("[AI] Game đã kết thúc, không có nước đi.", file=sys.stderr)
        print(json.dumps({"move": None}))
        return

    # Chọn nước đi
    move = choose_move(data)

    # In kết quả ra stdout (PHẢI là JSON hợp lệ duy nhất)
    print(json.dumps({"move": move}))


if __name__ == '__main__':
    main()
