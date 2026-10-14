"""Framework-independent Battlecode rules (public coordinates are 1-based)."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

TYPES = ("rock", "paper", "scissors")
BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
DIRS = tuple((dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)


def _classic_pieces(rows=9, cols=9):
    layout = (("scissors", "rock", "paper"), ("paper", "scissors", "rock"), ("rock", "paper", "scissors"))
    result, counts = [], {"P1": Counter(), "P2": Counter()}
    for owner, origin, reverse in (("P1", (1, 1), False), ("P2", (rows - 2, cols - 2), True)):
        for r in range(3):
            for c in range(3):
                kind = layout[r][c]
                counts[owner][kind] += 1
                rr, cc = (2 - r, 2 - c) if reverse else (r, c)
                result.append({"id": f"{owner}-{kind[0].upper()}{counts[owner][kind]}", "owner": owner,
                               "type": kind, "at": [origin[0] + rr, origin[1] + cc]})
    return result


def board_presets():
    classic = {"rows": 9, "cols": 9, "shape": "rectangle", "playable_cells": None,
               "blocked_cells": [], "goals": {"P1": [9, 9], "P2": [1, 1]},
               "initial_pieces": _classic_pieces()}
    rectangle = {"rows": 7, "cols": 11, "shape": "rectangle", "playable_cells": None,
                 "blocked_cells": [], "goals": {"P1": [7, 11], "P2": [1, 1]},
                 "initial_pieces": _classic_pieces(7, 11)}
    cells = [[r, c] for r in range(1, 10) for c in range(1, 10) if 4 <= r <= 6 or 4 <= c <= 6]
    # Teams use the two ends of the horizontal arm; all positions belong to the cross.
    cross = {"rows": 9, "cols": 9, "shape": "cross", "playable_cells": cells, "blocked_cells": [],
             "goals": {"P1": [5, 9], "P2": [5, 1]}, "initial_pieces": [
                 {"id": "P1-R1", "owner": "P1", "type": "rock", "at": [4, 1]},
                 {"id": "P1-P1", "owner": "P1", "type": "paper", "at": [5, 2]},
                 {"id": "P1-S1", "owner": "P1", "type": "scissors", "at": [6, 1]},
                 {"id": "P2-R1", "owner": "P2", "type": "rock", "at": [6, 9]},
                 {"id": "P2-P1", "owner": "P2", "type": "paper", "at": [5, 8]},
                 {"id": "P2-S1", "owner": "P2", "type": "scissors", "at": [4, 9]}]}
    obstacles = deepcopy(classic)
    obstacles.update({"shape": "obstacles", "blocked_cells": [[4, 5], [5, 4], [5, 6], [6, 5]]})
    return {"classic_9x9": classic, "rectangle_7x11": rectangle, "cross_9x9": cross,
            "obstacles_9x9": obstacles}


def validate_board_config(config):
    try:
        rows, cols = config["rows"], config["cols"]
        if not isinstance(rows, int) or not isinstance(cols, int) or rows < 1 or cols < 1:
            raise ValueError("rows và cols phải là số nguyên dương")
        playable = config.get("playable_cells")
        playable_set = None if playable is None else {tuple(x) for x in playable}
        def inside(cell):
            r, c = cell
            return 1 <= r <= rows and 1 <= c <= cols and (playable_set is None or cell in playable_set)
        blocked = {tuple(x) for x in config.get("blocked_cells", [])}
        if any(not inside(x) for x in blocked): raise ValueError("obstacle ngoài vùng chơi")
        goals = config["goals"]
        if set(goals) != {"P1", "P2"} or any(not inside(tuple(goals[p])) or tuple(goals[p]) in blocked for p in goals):
            raise ValueError("đích không hợp lệ")
        seen_ids, seen_cells = set(), set()
        for piece in config["initial_pieces"]:
            if piece.get("owner") not in ("P1", "P2") or piece.get("type") not in TYPES or not piece.get("id"):
                raise ValueError("quân khởi tạo không hợp lệ")
            cell = tuple(piece.get("at", []))
            if piece["id"] in seen_ids or cell in seen_cells or not inside(cell) or cell in blocked:
                raise ValueError("quân khởi tạo trùng hoặc ở ô không hợp lệ")
            seen_ids.add(piece["id"]); seen_cells.add(cell)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Cấu hình bàn không hợp lệ: {exc}") from exc


class GameState:
    def __init__(self, board_config=None, max_plies=300):
        self.board = deepcopy(board_config or board_presets()["classic_9x9"])
        validate_board_config(self.board)
        self.pieces = deepcopy(self.board["initial_pieces"])
        self.current_player, self.ply, self.max_plies = "P1", 0, max_plies
        self.status, self.winner, self.result, self.reason = "playing", None, None, None
        self.repetitions = Counter(); self._mark_position()

    @property
    def finished(self): return self.status == "finished"

    def _cell_map(self): return {tuple(p["at"]): p for p in self.pieces}
    def _playable(self, cell):
        r, c = cell
        cells = self.board.get("playable_cells")
        return 1 <= r <= self.board["rows"] and 1 <= c <= self.board["cols"] and (cells is None or list(cell) in cells) and list(cell) not in self.board.get("blocked_cells", [])
    def _key(self): return (self.current_player, tuple(sorted((p["id"], p["owner"], p["type"], *p["at"]) for p in self.pieces)))
    def _mark_position(self): self.repetitions[self._key()] += 1
    def legal_moves(self, player=None):
        player = player or self.current_player; cells = self._cell_map(); moves = []
        for piece in self.pieces:
            if piece["owner"] != player: continue
            fr = piece["at"]
            for dr, dc in DIRS:
                to = [fr[0] + dr, fr[1] + dc]
                if not self._playable(tuple(to)): continue
                target = cells.get(tuple(to))
                if target and target["owner"] == player: continue
                if target and BEATS[piece["type"]] != target["type"]: continue
                capture = target is not None
                moves.append({"piece_id": piece["id"], "from": list(fr), "to": to,
                              "capture_piece_id": target["id"] if target else None, "capture": capture,
                              "wins_immediately": to == self.board["goals"][player] or (capture and len([p for p in self.pieces if p["owner"] != player]) == 1)})
        return moves
    def finish(self, winner, result, code, message):
        self.status, self.winner, self.result = "finished", winner, result
        self.reason = {"code": code, "message": message}
    def check_turn_start(self):
        if not self.finished and not self.legal_moves():
            other = "P2" if self.current_player == "P1" else "P1"
            self.finish(other, "win", "no_legal_moves", f"{self.current_player} thua do hết nước đi")
        return self.finished
    def apply_move(self, proposed):
        legal = self.legal_moves()
        match = next((m for m in legal if isinstance(proposed, dict) and all(proposed.get(k) == m[k] for k in ("piece_id", "from", "to"))), None)
        if not match: raise ValueError("Nước đi không nằm trong legal_moves")
        player, cells = self.current_player, self._cell_map(); piece = next(p for p in self.pieces if p["id"] == match["piece_id"])
        captured = cells.get(tuple(match["to"])); piece["at"] = match["to"]
        if captured: self.pieces.remove(captured)
        self.ply += 1
        event = {"type": "move", "ply": self.ply, "player": player, "piece_id": piece["id"], "piece_type": piece["type"], "from": match["from"], "to": match["to"], "captured_piece": deepcopy(captured), "message": f"{player}: {piece['type']} {match['from']} → {match['to']}"}
        if match["to"] == self.board["goals"][player]: self.finish(player, "win", "goal_reached", f"{player} đến đích")
        elif not any(p["owner"] != player for p in self.pieces): self.finish(player, "win", "all_pieces_captured", f"{player} bắt hết quân đối thủ")
        elif self.ply >= self.max_plies: self.finish(None, "draw", "max_plies", "Hòa do chạm giới hạn nước")
        else:
            self.current_player = "P2" if player == "P1" else "P1"; self._mark_position()
            if self.repetitions[self._key()] >= 3: self.finish(None, "draw", "threefold_repetition", "Hòa do lặp trạng thái 3 lần")
            else: self.check_turn_start()
        event["state_after"] = self.snapshot(); return event
    def snapshot(self):
        return {"board": {k: deepcopy(v) for k, v in self.board.items() if k != "initial_pieces"}, "pieces": deepcopy(self.pieces), "current_player": self.current_player, "ply": self.ply, "status": self.status, "winner": self.winner, "result": self.result, "reason": deepcopy(self.reason)}
    def bot_input(self, match_id, userdata=None):
        players = {p: {"goal": self.board["goals"][p], "pieces": [{"id": x["id"], "type": x["type"], "at": x["at"]} for x in self.pieces if x["owner"] == p]} for p in ("P1", "P2")}
        return {"protocol_version": "1.0", "match_id": match_id, "turn": self.ply // 2 + 1, "ply": self.ply, "current_player": self.current_player, "board": {k: deepcopy(v) for k, v in self.board.items() if k != "initial_pieces"}, "players": players, "legal_moves": self.legal_moves(), "userdata": userdata}
