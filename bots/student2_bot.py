"""Deterministic example bot: choose the final legal move."""
import json
import sys

state = json.load(sys.stdin)
moves = state["legal_moves"]
move = moves[-1] if moves else None
print(json.dumps({"move": None} if move is None else {"move": {key: move[key] for key in ("piece_id", "from", "to")}, "userdata": {"turns_seen": state["ply"]}}))
