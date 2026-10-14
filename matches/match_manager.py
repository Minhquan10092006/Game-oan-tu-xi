from __future__ import annotations
import shutil, tempfile, uuid
from pathlib import Path
from .bot_runner import BotError, BotRunner
from .game_engine import GameState, board_presets

class MatchManager:
    """Runs all plies first, retaining immutable replay snapshots for the UI."""
    def run(self, p1_source, p2_source, preset="classic_9x9", max_plies=300, timeout=2.0, match_id=None):
        if preset not in board_presets(): raise ValueError("Preset không tồn tại")
        match_id = match_id or f"match-{uuid.uuid4().hex[:12]}"; root = Path(tempfile.mkdtemp(prefix="ott-battle-"))
        state, events, userdata, runs = GameState(board_presets()[preset], max_plies), [], {"P1": None, "P2": None}, []
        runners, preparation_errors = {}, {}
        for player, source in (("P1", p1_source), ("P2", p2_source)):
            try:
                runners[player] = BotRunner(source, root / player, timeout)
            except BotError as e:
                preparation_errors[player] = e
        if preparation_errors:
            if len(preparation_errors) == 2:
                state.finish(None, "error", "bot_initialization_failed", "Cả hai bot không thể khởi tạo")
            else:
                failed, error = next(iter(preparation_errors.items()))
                state.finish("P2" if failed == "P1" else "P1", "forfeit", error.code, f"{failed} thua: {error.message}")
            result = self._result(match_id, preset, state, events, runs); shutil.rmtree(root, ignore_errors=True); return result
        events.append({"type": "started", "state_after": state.snapshot()})
        while not state.finished:
            if state.check_turn_start(): break
            player = state.current_player
            try:
                output, run = runners[player].run_turn(state.bot_input(match_id, userdata[player])); runs.append({"player": player, **run})
                event = state.apply_move(output["move"]); userdata[player] = output.get("userdata")
            except BotError as e:
                state.finish("P2" if player == "P1" else "P1", "forfeit", e.code, f"{player} thua do {e.message}")
                runs.append({"player": player, "stderr": e.stderr, "error": e.code}); break
            except ValueError as e:
                state.finish("P2" if player == "P1" else "P1", "forfeit", "illegal_move", f"{player} thua do nước đi không hợp lệ: {e}"); break
            events.append(event)
        events.append({"type": "finished", "winner": state.winner, "result": state.result, "reason": state.reason, "final_state": state.snapshot()})
        result = self._result(match_id, preset, state, events, runs)
        shutil.rmtree(root, ignore_errors=True)
        return result
    @staticmethod
    def _result(match_id, preset, state, events, runs):
        return {"id": match_id, "status": state.status, "board_preset": preset, "ply": state.ply, "winner": state.winner, "result": state.result, "reason": state.reason, "events": events, "state": state.snapshot(), "bot_runs": runs}
