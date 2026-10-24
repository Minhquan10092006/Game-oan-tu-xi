"""
SpeedrunMaster (The Grandmaster / Speedrunner) - Chiến thuật Đột kích đích & Hộ tống thông minh.
Tác giả: Antigravity AI
Nguyên lý:
1. Thắng ngay lập tức nếu có nước đi vào đích hoặc ăn quân quyết định.
2. Thiết lập "Quân tiên phong" (Spearhead Runner) tiến nhanh nhất về đích.
3. Cơ chế Hộ tống (Escort Convoy): Quân đồng minh đi kèm để bảo kê và diệt kẻ săn mồi của Quân tiên phong.
4. Thủ thành (Base Sentry): Duy trì chốt chặn gần đích nhà, không để đối thủ lén về đích.
5. Minimax 1-ply Counter-attack: Trừ điểm dựa trên đòn phản công mạnh nhất của đối thủ ở lượt sau.
6. Bộ nhớ userdata ghi nhớ mục tiêu và ngăn ngừa hòa lặp cờ 3 lần.
"""
import sys
import json
from collections import Counter

BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
BEATEN_BY = {"scissors": "rock", "paper": "scissors", "rock": "paper"}


def chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def is_threatened(pos, piece_type, enemies, excluded_id=None):
    predator = BEATEN_BY[piece_type]
    for e in enemies:
        if e["id"] == excluded_id:
            continue
        if e["type"] == predator and chebyshev(e["at"], pos) == 1:
            return True
    return False


def get_enemy_counter_score(future_pieces, my_player, enemy_player, enemies, my_goal, my_counts):
    """Ước lượng đòn phản công mạnh nhất của đối thủ sau khi ta đi nước này."""
    enemy_best_score = 0
    my_positions = {tuple(p["at"]): p for p in future_pieces}

    for e in enemies:
        e_type = e["type"]
        e_pos = e["at"]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                to = (e_pos[0] + dr, e_pos[1] + dc)
                # Đối thủ về đích thắng ngay
                if list(to) == my_goal:
                    return 999999
                # Đối thủ ăn quân ta
                target = my_positions.get(to)
                if target and BEATS[e_type] == target["type"]:
                    # Mất quân duy nhất của 1 loại = THUA TRẬN NGAY LẬP TỨC!
                    if my_counts[target["type"]] == 1:
                        return 850000
                    capture_val = 22000
                    if my_counts[target["type"]] == 2:
                        capture_val += 30000
                    if chebyshev(target["at"], my_goal) <= 3:
                        capture_val += 15000
                    if capture_val > enemy_best_score:
                        enemy_best_score = capture_val
    return enemy_best_score


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

    userdata = state.get("userdata") or {}
    history = userdata.get("history", {})

    # 1. THẮNG NGAY NẾU CÓ THỂ
    for m in legal_moves:
        if m.get("wins_immediately"):
            return m, userdata

    # 2. XÁC ĐỊNH QUÂN TIÊN PHONG (SPEARHEAD RUNNER)
    # Quân đang ở gần my_goal nhất và có đường chạy thoáng
    safe_runners = [p for p in my_pieces if not is_threatened(p["at"], p["type"], enemies)]
    candidate_runners = safe_runners if safe_runners else my_pieces
    spearhead = min(candidate_runners, key=lambda p: chebyshev(p["at"], my_goal))
    spearhead_id = spearhead["id"]

    scored_moves = []
    for m in legal_moves:
        score = 0
        p = piece_map[m["piece_id"]]
        p_type = p["type"]
        fr = m["from"]
        to = m["to"]
        capture_id = m.get("capture_piece_id")
        captured = enemy_map.get(capture_id) if capture_id else None

        dist_cur = chebyshev(fr, my_goal)
        dist_new = chebyshev(to, my_goal)
        progress = dist_cur - dist_new

        # A. Điểm số tiến bước về đích
        if p["id"] == spearhead_id:
            # Quân tiên phong được ưu tiên tối thượng lao về đích
            score += progress * 4000
            score -= dist_new * 500
        else:
            score += progress * 1200
            score -= dist_new * 150

        # B. Điểm ăn quân
        if captured:
            score += 14000
            # Ăn quân đe dọa hoặc chặn đường tiến
            if chebyshev(captured["at"], my_goal) < dist_cur:
                score += 8000
            # Ăn quân thuộc loại đối thủ chỉ còn ít con
            if enemy_counts[captured["type"]] <= 2:
                score += 15000

        # C. Cơ chế hộ tống (Escort):
        # Nếu không phải là tiên phong, đi theo che chắn cho quân tiên phong
        if p["id"] != spearhead_id and spearhead:
            # Quân này bảo vệ loài của spearhead:
            predator_of_spearhead = BEATEN_BY[spearhead["type"]]
            if p_type == BEATEN_BY[predator_of_spearhead]:
                # Giữ cự ly 1-2 ô quanh spearhead
                dist_to_spearhead = chebyshev(to, spearhead["at"])
                if dist_to_spearhead in (1, 2):
                    score += 3500

        # D. Thủ thành (Base Sentry)
        # Giữ ít nhất 1 quân gần đích nhà để cản đối thủ
        dist_to_enemy_goal = chebyshev(to, enemy_goal)
        if dist_to_enemy_goal <= 2:
            score += 1500

        # E. Kiểm tra hiểm họa trực tiếp cho bản thân
        if is_threatened(to, p_type, enemies, excluded_id=capture_id):
            if my_counts[p_type] == 1:
                score -= 900000  # Nguy cơ tuyệt chủng
            elif my_counts[p_type] == 2:
                score -= 35000
            else:
                score -= 16000

        # F. Mô phỏng đòn phản công của đối thủ (Minimax 1-ply)
        # Giả lập vị trí các quân sau khi ta đi
        future_my_pieces = []
        for piece_item in my_pieces:
            if piece_item["id"] == p["id"]:
                future_my_pieces.append({"id": p["id"], "type": p_type, "at": to})
            else:
                future_my_pieces.append(piece_item)
        remaining_enemies = [e for e in enemies if e["id"] != capture_id]

        counter_damage = get_enemy_counter_score(future_my_pieces, player, other, remaining_enemies, my_goal, my_counts)
        score -= counter_damage

        # G. Tránh lặp trạng thái
        pos_key = f"{p['id']}:{to[0]},{to[1]}"
        seen = history.get(pos_key, 0)
        if seen >= 2:
            score -= 150000
        elif seen == 1:
            score -= 6000

        scored_moves.append((score, m, pos_key))

    scored_moves.sort(key=lambda x: x[0], reverse=True)
    best_score, best_move, best_pos_key = scored_moves[0]

    history[best_pos_key] = history.get(best_pos_key, 0) + 1
    userdata["history"] = history

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
        sys.stderr.write(f"Error in SpeedrunMaster: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
