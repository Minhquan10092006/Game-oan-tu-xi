"""
matches/tests.py
----------------
Test game engine Python wrapper.
"""
from django.test import TestCase
from .engine import (
    GameState, Piece, BEATS, GOALS, DIRECTIONS,
    build_ai_input, parse_ai_output, validate_ai_move,
)


class TestPiece(TestCase):
    def test_beats_rock_beats_scissors(self):
        rock = Piece(1, 'rock')
        scissors = Piece(2, 'scissors')
        self.assertTrue(rock.beats(scissors))

    def test_beats_scissors_beats_paper(self):
        scissors = Piece(1, 'scissors')
        paper = Piece(2, 'paper')
        self.assertTrue(scissors.beats(paper))

    def test_beats_paper_beats_rock(self):
        paper = Piece(1, 'paper')
        rock = Piece(2, 'rock')
        self.assertTrue(paper.beats(rock))

    def test_same_player_never_beats(self):
        rock1 = Piece(1, 'rock')
        scissors1 = Piece(1, 'scissors')
        self.assertFalse(rock1.beats(scissors1))

    def test_same_type_does_not_beat(self):
        rock1 = Piece(1, 'rock')
        rock2 = Piece(2, 'rock')
        self.assertFalse(rock1.beats(rock2))
        self.assertFalse(rock2.beats(rock1))

    def test_clone_preserves_id(self):
        p = Piece(1, 'paper')
        c = p.clone()
        self.assertEqual(p.id, c.id)
        self.assertEqual(p.type, c.type)

    def test_to_dict_from_dict(self):
        p = Piece(2, 'scissors')
        d = p.to_dict()
        p2 = Piece.from_dict(d)
        self.assertEqual(p.player, p2.player)
        self.assertEqual(p.type, p2.type)
        self.assertEqual(p.id, p2.id)


class TestGameStateInit(TestCase):
    def setUp(self):
        self.state = GameState()

    def test_board_size(self):
        self.assertEqual(len(self.state.board), 9)
        for row in self.state.board:
            self.assertEqual(len(row), 9)

    def test_initial_player(self):
        self.assertEqual(self.state.current_player, 1)
        self.assertEqual(self.state.turn_number, 1)

    def test_each_player_has_9_pieces(self):
        p1 = self.state.count_pieces(1)
        p2 = self.state.count_pieces(2)
        self.assertEqual(p1['total'], 9)
        self.assertEqual(p2['total'], 9)

    def test_each_player_has_3_of_each_type(self):
        for player in (1, 2):
            counts = self.state.count_pieces(player)
            self.assertEqual(counts['rock'], 3)
            self.assertEqual(counts['paper'], 3)
            self.assertEqual(counts['scissors'], 3)

    def test_p1_pieces_in_top_left(self):
        for r in range(3):
            for c in range(3):
                p = self.state.board[r][c]
                self.assertIsNotNone(p)
                self.assertEqual(p.player, 1)

    def test_p2_pieces_in_bottom_right(self):
        for r in range(6, 9):
            for c in range(6, 9):
                p = self.state.board[r][c]
                self.assertIsNotNone(p)
                self.assertEqual(p.player, 2)

    def test_goals_correct(self):
        self.assertEqual(GOALS[1], {'row': 8, 'col': 8})
        self.assertEqual(GOALS[2], {'row': 0, 'col': 0})


class TestValidateMove(TestCase):
    def setUp(self):
        self.state = GameState()

    def test_valid_move_to_empty_cell(self):
        # P1 rock tại (2,0) → (3,0) (empty)
        result = self.state.validate_move(2, 0, 3, 0)
        self.assertTrue(result['valid'])
        self.assertFalse(result.get('is_capture', False))

    def test_out_of_bounds(self):
        result = self.state.validate_move(0, 0, -1, 0)
        self.assertFalse(result['valid'])

    def test_move_more_than_1_step(self):
        result = self.state.validate_move(0, 0, 0, 2)
        self.assertFalse(result['valid'])

    def test_move_to_own_piece(self):
        # (0,0) và (0,1) đều là P1
        result = self.state.validate_move(0, 0, 0, 1)
        self.assertFalse(result['valid'])

    def test_capture_opponent(self):
        # Rock tại (2,0) thắng Scissors. Setup manual capture.
        state = GameState()
        # Đặt P2 scissors tại (3,0) (empty cell)
        state.board[3][0] = Piece(2, 'scissors')
        result = state.validate_move(2, 0, 3, 0)  # P1 rock → ăn P2 scissors
        self.assertTrue(result['valid'])
        self.assertTrue(result.get('is_capture', False))

    def test_blocked_same_type(self):
        # P1 rock và P2 rock cạnh nhau → blocked
        state = GameState()
        state.board[3][0] = Piece(2, 'rock')
        result = state.validate_move(2, 0, 3, 0)  # P1 rock → P2 rock
        self.assertFalse(result['valid'])
        self.assertTrue(result.get('blocked', False))

    def test_cannot_move_into_stronger_opponent(self):
        # P1 scissors không thể di chuyển vào P2 rock (rock > scissors)
        state = GameState()
        state.board[0][0] = Piece(1, 'scissors')
        state.board[1][0] = Piece(2, 'rock')
        result = state.validate_move(0, 0, 1, 0)
        self.assertFalse(result['valid'])

    def test_wrong_player_turn(self):
        # P2 cố đi khi lượt P1
        state = GameState()
        result = state.validate_move(8, 8, 7, 8)  # P2 piece
        self.assertFalse(result['valid'])


class TestExecuteMove(TestCase):
    def test_execute_valid_move(self):
        state = GameState()
        # P1 (2,0) → (3,0)
        record = state.execute_move(2, 0, 3, 0)
        self.assertIsNotNone(record)
        self.assertIsNone(state.board[2][0])
        self.assertIsNotNone(state.board[3][0])
        self.assertEqual(state.board[3][0].player, 1)

    def test_execute_invalid_move_returns_none(self):
        state = GameState()
        result = state.execute_move(0, 0, 0, 5)  # quá xa
        self.assertIsNone(result)

    def test_turn_switches_after_move(self):
        state = GameState()
        state.execute_move(2, 0, 3, 0)
        self.assertEqual(state.current_player, 2)

    def test_turn_number_increments_after_p2_move(self):
        state = GameState()
        state.execute_move(2, 0, 3, 0)  # P1
        state.execute_move(6, 8, 5, 8)  # P2
        self.assertEqual(state.turn_number, 2)

    def test_capture_removes_piece(self):
        state = GameState()
        state.board[3][0] = Piece(2, 'scissors')
        record = state.execute_move(2, 0, 3, 0)  # P1 rock ăn P2 scissors
        self.assertIsNotNone(record)
        self.assertTrue(record['is_capture'])
        self.assertEqual(state.count_pieces(2)['total'], 9)  # vẫn 9 vì chỉ thêm 1 ở setup

    def test_win_by_reaching_goal(self):
        state = GameState()
        # Đặt P1 piece ngay cạnh goal (8,8)
        state.board[7][8] = Piece(1, 'rock')
        state.current_player = 1
        record = state.execute_move(7, 8, 8, 8)
        self.assertTrue(state.game_over)
        self.assertEqual(state.winner, 1)

    def test_win_by_eliminating_all_opponents(self):
        state = GameState()
        # Xóa tất cả quân P2, chỉ còn 1
        for r in range(9):
            for c in range(9):
                p = state.board[r][c]
                if p and p.player == 2:
                    state.board[r][c] = None
        # Đặt 1 quân P2 cạnh P1 rock để P1 ăn
        state.board[3][0] = Piece(2, 'scissors')
        state.execute_move(2, 0, 3, 0)
        self.assertTrue(state.game_over)
        self.assertEqual(state.winner, 1)


class TestGetAllLegalMoves(TestCase):
    def test_initial_state_has_legal_moves(self):
        state = GameState()
        moves = state.get_all_legal_moves()
        self.assertGreater(len(moves), 0)

    def test_all_moves_are_valid(self):
        state = GameState()
        moves = state.get_all_legal_moves()
        for move in moves:
            result = state.validate_move(
                move['from_row'], move['from_col'],
                move['to_row'], move['to_col'],
            )
            self.assertTrue(result['valid'], f'Move {move} không hợp lệ')


class TestSerialization(TestCase):
    def test_to_dict_from_dict_roundtrip(self):
        state = GameState()
        state.execute_move(2, 0, 3, 0)
        d = state.to_dict()
        state2 = GameState.from_dict(d)
        self.assertEqual(state2.current_player, state.current_player)
        self.assertEqual(state2.turn_number, state.turn_number)
        self.assertEqual(state2.game_over, state.game_over)
        # Board
        for r in range(9):
            for c in range(9):
                p1 = state.board[r][c]
                p2 = state2.board[r][c]
                self.assertEqual(p1 is None, p2 is None)
                if p1:
                    self.assertEqual(p1.player, p2.player)
                    self.assertEqual(p1.type, p2.type)


class TestBuildAIInput(TestCase):
    def test_build_ai_input_structure(self):
        state = GameState()
        ai_input = build_ai_input(state)
        self.assertIn('board', ai_input)
        self.assertIn('current_player', ai_input)
        self.assertIn('legal_moves', ai_input)
        self.assertIn('goal', ai_input)
        self.assertIn('opponent_goal', ai_input)
        self.assertEqual(len(ai_input['board']), 9)
        self.assertEqual(len(ai_input['board'][0]), 9)

    def test_legal_moves_in_input_are_all_valid(self):
        state = GameState()
        ai_input = build_ai_input(state)
        for move in ai_input['legal_moves']:
            result = state.validate_move(
                move['from_row'], move['from_col'],
                move['to_row'], move['to_col'],
            )
            self.assertTrue(result['valid'])


class TestParseAIOutput(TestCase):
    def test_valid_output(self):
        raw = '{"move": {"from_row": 2, "from_col": 0, "to_row": 3, "to_col": 0}}'
        move = parse_ai_output(raw)
        self.assertIsNotNone(move)
        self.assertEqual(move['from_row'], 2)
        self.assertEqual(move['to_row'], 3)

    def test_invalid_json(self):
        move = parse_ai_output('not json')
        self.assertIsNone(move)

    def test_empty_output(self):
        move = parse_ai_output('')
        self.assertIsNone(move)

    def test_missing_move_key(self):
        move = parse_ai_output('{"from_row": 0}')
        self.assertIsNone(move)

    def test_missing_required_field(self):
        move = parse_ai_output('{"move": {"from_row": 0, "from_col": 0, "to_row": 1}}')
        self.assertIsNone(move)

    def test_wrong_type_for_coords(self):
        move = parse_ai_output('{"move": {"from_row": "a", "from_col": 0, "to_row": 1, "to_col": 0}}')
        self.assertIsNone(move)

    def test_extra_fields_accepted(self):
        """Output có thêm fields khác vẫn được chấp nhận."""
        raw = '{"move": {"from_row": 2, "from_col": 0, "to_row": 3, "to_col": 0, "comment": "debug"}}'
        move = parse_ai_output(raw)
        self.assertIsNotNone(move)


class TestValidateAIMove(TestCase):
    def test_valid_move_accepted(self):
        state = GameState()
        move = {'from_row': 2, 'from_col': 0, 'to_row': 3, 'to_col': 0}
        result = validate_ai_move(state, move)
        self.assertTrue(result['valid'])

    def test_out_of_bounds_rejected(self):
        state = GameState()
        move = {'from_row': 0, 'from_col': 0, 'to_row': -1, 'to_col': 0}
        result = validate_ai_move(state, move)
        self.assertFalse(result['valid'])

    def test_none_move_rejected(self):
        state = GameState()
        result = validate_ai_move(state, None)
        self.assertFalse(result['valid'])

    def test_move_to_own_piece_rejected(self):
        state = GameState()
        move = {'from_row': 0, 'from_col': 0, 'to_row': 0, 'to_col': 1}
        result = validate_ai_move(state, move)
        self.assertFalse(result['valid'])
