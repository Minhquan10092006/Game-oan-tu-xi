"""Deterministic example bot: take a winning move, otherwise first legal move."""
import json
import sys

state = json.load(sys.stdin)
moves = state["legal_moves"]
move = next((m for m in moves if m["wins_immediately"]), moves[0] if moves else None)
if move is None:
    print(json.dumps({"move": None}))
else:
    print(json.dumps({"move": {key: move[key] for key in ("piece_id", "from", "to")}, "userdata": state.get("userdata")}))
