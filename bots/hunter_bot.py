"""
HunterBot (The Predator) - Chiến thuật Sát thủ diệt chủng & Kiểm soát thế trận.
Tác giả: Antigravity AI
Nguyên lý:
1. Bắt quân thắng ngay nếu có cơ hội (chạm đích hoặc diệt sạch 1 loại quân).
2. Phân tích loại quân ít nhất của đối thủ để ưu tiên truy sát (Type Elimination).
3. Bảo vệ cẩn mật loại quân ít nhất của phe mình (chống bị diệt chủng).
4. Phân tích hiểm họa (Threat Analysis): né ô bị đối thủ bắt ở lượt sau.
5. Bộ nhớ userdata chống lặp hòa 3 lần (Threefold Repetition Avoidance).
"""
import sys
import json
from collections import Counter

BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
BEATEN_BY = {"scissors": "rock", "paper": "scissors", "rock": "paper"}


def chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def is_threatened_at(pos, piece_type, enemies, my_pieces, excluded_enemy_id=None):
    """Kiểm tra xem tại vị trí pos, quân piece_type có nguy cơ bị đối thủ ăn ở lượt sau không."""
    threatened = False
    predator_type = BEATEN_BY[piece_type]

    for enemy in enemies:
        if enemy["id"] == excluded_enemy_id:
            continue
        # Kẻ săn mồi có thể đi 1 bước tới pos
        if enemy["type"] == predator_type and chebyshev(enemy["at"], pos) == 1:
            threatened = True
            break
    return threatened


def count_defenders(pos, piece_type, my_pieces, moving_piece_id):
    """Đếm số quân đồng minh có thể bảo kê ô pos nếu có kẻ địch dám tới ăn."""
    predator_of_my_piece = BEATEN_BY[piece_type]
    defender_type = BEATEN_BY[predator_of_my_piece]  # Quân đồng minh có thể ăn kẻ săn mồi
    defenders = 0
    for p in my_pieces:
        if p["id"] == moving_piece_id:
            continue
        if p["type"] == defender_type and chebyshev(p["at"], pos) <= 1:
            defenders += 1
    return defenders


def choose_move(state):
    legal_moves = state.get("legal_moves", [])
    if not legal_moves:
        return None, {}

    player = state["current_player"]
    other = "P2" if player == "P1" else "P1"
    my_goal = state["players"][player]["goal"]
    enemy_goal = state["players"][other]["goal"]

    my_pieces = state["players"][player]["pieces"]
    enemies = state["players"][other]["pieces"]

    my_counts = Counter(p["type"] for p in my_pieces)
    enemy_counts = Counter(p["type"] for p in enemies)

    piece_map = {p["id"]: p for p in my_pieces}
    enemy_map = {e["id"]: e for e in enemies}
    enemy_pos_map = {tuple(e["at"]): e for e in enemies}

    # Đọc bộ nhớ userdata
    userdata = state.get("userdata") or {}
    history = userdata.get("pos_history", {})

    # Xác định loại quân mục tiêu của đối thủ (loại còn ít con nhất)
    # Nếu đối thủ còn 1 con -> cơ hội kết liễu
    weakest_enemy_type = min(enemy_counts.keys(), key=lambda t: enemy_counts[t]) if enemy_counts else None
    weakest_enemy_count = enemy_counts.get(weakest_enemy_type, 99)

    # 1. KIỂM TRA NƯỚC THẮNG TỨC THÌ
    for m in legal_moves:
        if m.get("wins_immediately"):
            return m, userdata

    # 2. CHẤM ĐIỂM TỪNG NƯỚC ĐI TIỀM NĂNG
    scored_moves = []
    for m in legal_moves:
        score = 0
        piece = piece_map[m["piece_id"]]
        p_type = piece["type"]
        fr = m["from"]
        to = m["to"]
        capture_id = m.get("capture_piece_id")
        captured_enemy = enemy_map.get(capture_id) if capture_id else None

        # A. Giá trị ăn quân
        if captured_enemy:
            c_type = captured_enemy["type"]
            # Ăn quân cơ bản
            score += 12000
            # Ăn quân thuộc loại yếu nhất của đối thủ (cực kỳ giá trị!)
            if c_type == weakest_enemy_type:
                score += 30000 if weakest_enemy_count == 2 else 15000
            # Ăn quân đang ở gần đích của đối thủ (chặn đường địch)
            score += max(0, 10 - chebyshev(captured_enemy["at"], my_goal)) * 500

        # B. Phân tích an toàn sau khi đi (Threat Analysis)
        threatened = is_threatened_at(to, p_type, enemies, my_pieces, excluded_enemy_id=capture_id)
        if threatened:
            defenders = count_defenders(to, p_type, my_pieces, piece["id"])
            # Nếu quân này là con duy nhất của loại mình -> TUYỆT ĐỐI KHÔNG ĐƯỢC CHẾT!
            if my_counts[p_type] == 1:
                score -= 800000
            elif my_counts[p_type] == 2:
                score -= 40000
            else:
                score -= 15000 if defenders == 0 else 5000

        # C. Thoát hiểm: Nếu ở vị trí cũ fr đang bị đe dọa, rời đi là điểm cộng
        if is_threatened_at(fr, p_type, enemies, my_pieces):
            if not threatened:
                score += 18000 if my_counts[p_type] == 1 else 8000

        # D. Truy sát loại quân mục tiêu của đối thủ
        if weakest_enemy_type and BEATS[p_type] == weakest_enemy_type:
            # Quân của ta là khắc tinh của loại địch đang yếu thế -> tiến lại gần chúng
            targets = [e for e in enemies if e["type"] == weakest_enemy_type]
            if targets:
                closest_target = min(targets, key=lambda t: chebyshev(to, t["at"]))
                dist_after = chebyshev(to, closest_target["at"])
                dist_before = chebyshev(fr, closest_target["at"])
                score += (dist_before - dist_after) * 1200
                score -= dist_after * 250

        # E. Tiến về đích (Progress towards Goal)
        cur_goal_dist = chebyshev(fr, my_goal)
        new_goal_dist = chebyshev(to, my_goal)
        progress = cur_goal_dist - new_goal_dist
        score += progress * 1500 - new_goal_dist * 200

        # F. Chặn đối thủ về đích (Defensive screening)
        for enemy in enemies:
            enemy_to_goal = chebyshev(enemy["at"], my_goal)
            if enemy_to_goal <= 3:  # Đối thủ đang áp sát đích của mình
                # Thưởng nếu quân ta chặn trước mặt hoặc tiến đến áp sát quân địch nguy hiểm
                if chebyshev(to, enemy["at"]) <= 1:
                    if BEATS[p_type] == enemy["type"]:
                        score += 9000  # Đứng đe dọa ăn luôn địch
                    elif p_type == enemy["type"]:
                        score += 3000  # Cản đường

        # G. Tránh lặp trạng thái hòa 3 lần
        pos_key = f"{piece['id']}:{to[0]},{to[1]}"
        seen_count = history.get(pos_key, 0)
        if seen_count >= 2:
            score -= 100000  # Phạt nặng nước đi dẫn đến lặp lần 3
        elif seen_count == 1:
            score -= 5000

        scored_moves.append((score, m, pos_key))

    # Chọn nước có điểm số cao nhất
    scored_moves.sort(key=lambda x: x[0], reverse=True)
    best_score, best_move, best_pos_key = scored_moves[0]

    # Cập nhật lịch sử vị trí vào userdata
    history[best_pos_key] = history.get(best_pos_key, 0) + 1
    userdata["pos_history"] = history

    return best_move, userdata


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        state = json.loads(raw)
        move, userdata = choose_move(state)
        result = {
            "move": {k: move[k] for k in ("piece_id", "from", "to")} if move else None,
            "userdata": userdata,
        }
        print(json.dumps(result, separators=(",", ":")))
    except Exception as exc:
        sys.stderr.write(f"Error in HunterBot: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
