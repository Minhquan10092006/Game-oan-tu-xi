import json
import tempfile
from pathlib import Path
from django.test import SimpleTestCase
from .game_engine import GameState, board_presets, validate_board_config
from .match_manager import MatchManager

class GameEngineSpecTests(SimpleTestCase):
    def test_classic_is_one_based_and_has_nine_pieces_each(self):
        state = GameState()
        self.assertEqual(state.current_player, "P1")
        self.assertEqual(len([p for p in state.pieces if p["owner"] == "P1"]), 9)
        self.assertTrue(all(min(p["at"]) >= 1 for p in state.pieces))

    def test_cross_rejects_a_non_playable_destination(self):
        state = GameState(board_presets()["cross_9x9"])
        self.assertFalse(any(move["to"] == [1, 1] for move in state.legal_moves()))

    def test_engine_rejects_unlisted_move(self):
        with self.assertRaises(ValueError):
            GameState().apply_move({"piece_id": "P1-R1", "from": [1, 2], "to": [9, 9]})

    def test_invalid_config_is_detected(self):
        board = board_presets()["classic_9x9"]
        board["blocked_cells"] = [[1, 1]]
        with self.assertRaises(ValueError): validate_board_config(board)

    def test_runner_replays_two_python_bots(self):
        root = Path(__file__).resolve().parents[1]
        result = MatchManager().run(root / "bots/student1_bot.py", root / "bots/student2_bot.py", max_plies=8)
        self.assertEqual(result["status"], "finished")
        self.assertGreater(result["ply"], 0)
        self.assertEqual(result["reason"]["code"], "max_plies")
