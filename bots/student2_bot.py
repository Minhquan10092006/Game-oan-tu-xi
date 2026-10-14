"""Player 2: defensive counter-play plus progress toward its target."""
import json
import sys

BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}


def distance(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def choose(state):
    moves = state["legal_moves"]
    if not moves:
        return None
    player = state["current_player"]
    other = "P1" if player == "P2" else "P2"
    goal = state["players"][player]["goal"]
    own = {p["id"]: p for p in state["players"][player]["pieces"]}
    enemies = state["players"][other]["pieces"]
    enemy_at = {tuple(p["at"]): p for p in enemies}

    def score(move):
        piece = own[move["piece_id"]]
        captured = enemy_at.get(tuple(move["to"]))
        value = 1_000_000 if move["wins_immediately"] else 0
        if captured:
            value += 7_000 + 100 - 8 * distance(captured["at"], state["players"][other]["goal"])
        value += 100 * (distance(piece["at"], goal) - distance(move["to"], goal))
        value -= 1_700 * sum(
            BEATS[enemy["type"]] == piece["type"] and distance(enemy["at"], move["to"]) == 1
            for enemy in enemies
        )
        # Keep a response force near approaching enemies when no stronger action exists.
        value += sum(max(0, 5 - distance(move["to"], enemy["at"])) * 4 for enemy in enemies)
        return value

    ranked = sorted(moves, key=lambda move: (-score(move), move["piece_id"], move["to"]))
    best = [move for move in ranked if score(move) == score(ranked[0])]
    counter = int((state.get("userdata") or {}).get("tie_counter", 0))
    return best[counter % len(best)]


state = json.load(sys.stdin)
move = choose(state)
previous = state.get("userdata") or {}
result = {"move": None, "userdata": {"tie_counter": int(previous.get("tie_counter", 0)) + 1}}
if move:
    result["move"] = {key: move[key] for key in ("piece_id", "from", "to")}
print(json.dumps(result, separators=(",", ":")))
