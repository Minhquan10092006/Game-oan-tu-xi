"""
matches/engine.py
=================
Python port của server/engine.js.

Dùng để:
- Xác thực nước đi AI mà không cần gọi Node.js
- Tính danh sách nước đi hợp lệ để gửi cho AI làm input
- Chạy simulation trận đấu trong bộ chấm bài

Giữ NGUYÊN logic từ engine.js, không thay đổi luật chơi.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------ #
# Hằng số                                                             #
# ------------------------------------------------------------------ #

PIECE_TYPES = ('rock', 'paper', 'scissors')

# Quan hệ thắng: key thắng value
BEATS: dict[str, str] = {
    'rock': 'scissors',
    'scissors': 'paper',
    'paper': 'rock',
}

DIRECTIONS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
]

# Mục tiêu (0-indexed): P1 → (8,8), P2 → (0,0)
GOALS: dict[int, dict[str, int]] = {
    1: {'row': 8, 'col': 8},
    2: {'row': 0, 'col': 0},
}

_piece_counter = 0  # module-level counter (reset khi tạo GameState mới)


# ------------------------------------------------------------------ #
# Piece                                                               #
# ------------------------------------------------------------------ #

@dataclass
class Piece:
    player: int   # 1 hoặc 2
    type: str     # 'rock' | 'paper' | 'scissors'
    id: str = field(default='', repr=False)

    def __post_init__(self):
        if not self.id:
            global _piece_counter
            self.id = f'p{self.player}-{self.type}-{_piece_counter}'
            _piece_counter += 1

    def beats(self, other: 'Piece') -> bool:
        """Trả True nếu self thắng other (khác phe và khắc chế)."""
        if self.player == other.player:
            return False
        return BEATS[self.type] == other.type

    def same_type(self, other: 'Piece') -> bool:
        return self.type == other.type

    def clone(self) -> 'Piece':
        return Piece(player=self.player, type=self.type, id=self.id)

    def to_dict(self) -> dict:
        return {'player': self.player, 'type': self.type, 'id': self.id}

    @classmethod
    def from_dict(cls, d: dict) -> 'Piece':
        return cls(player=d['player'], type=d['type'], id=d.get('id', ''))


# ------------------------------------------------------------------ #
# GameState                                                           #
# ------------------------------------------------------------------ #

class GameState:
    """
    Trạng thái đầy đủ của một ván cờ.
    Mirror of GameState class in server/engine.js.
    """

    def __init__(self, setup: bool = True):
        global _piece_counter
        self.board: list[list[Optional[Piece]]] = self._create_empty_board()
        self.current_player: int = 1
        self.turn_number: int = 1
        self.move_history: list[dict] = []
        self.game_over: bool = False
        self.winner: Optional[int] = None
        self.win_reason: str = ''

        if setup:
            _piece_counter = 0
            self._setup_initial_pieces()

    # ---- Board setup ------------------------------------------------

    def _create_empty_board(self) -> list[list[Optional[Piece]]]:
        return [[None] * 9 for _ in range(9)]

    def _setup_initial_pieces(self):
        """
        Giống _setupInitialPieces trong engine.js.
        P1 góc trên-trái, P2 đối xứng 180° (8-row, 8-col).
        """
        p1_layout = [
            # Row 0
            {'row': 0, 'col': 0, 'type': 'scissors'},
            {'row': 0, 'col': 1, 'type': 'rock'},
            {'row': 0, 'col': 2, 'type': 'paper'},
            # Row 1
            {'row': 1, 'col': 0, 'type': 'paper'},
            {'row': 1, 'col': 1, 'type': 'scissors'},
            {'row': 1, 'col': 2, 'type': 'rock'},
            # Row 2
            {'row': 2, 'col': 0, 'type': 'rock'},
            {'row': 2, 'col': 1, 'type': 'paper'},
            {'row': 2, 'col': 2, 'type': 'scissors'},
        ]

        for item in p1_layout:
            self.board[item['row']][item['col']] = Piece(1, item['type'])

        for item in p1_layout:
            self.board[8 - item['row']][8 - item['col']] = Piece(2, item['type'])

    # ---- Accessors --------------------------------------------------

    def get_piece(self, row: int, col: int) -> Optional[Piece]:
        if 0 <= row <= 8 and 0 <= col <= 8:
            return self.board[row][col]
        return None

    def get_player_pieces(self, player: int) -> list[dict]:
        """Trả danh sách {'piece': Piece, 'row': int, 'col': int}."""
        result = []
        for r in range(9):
            for c in range(9):
                p = self.board[r][c]
                if p and p.player == player:
                    result.append({'piece': p, 'row': r, 'col': c})
        return result

    def count_pieces(self, player: int) -> dict[str, int]:
        counts: dict[str, int] = {'rock': 0, 'paper': 0, 'scissors': 0, 'total': 0}
        for r in range(9):
            for c in range(9):
                p = self.board[r][c]
                if p and p.player == player:
                    counts[p.type] += 1
                    counts['total'] += 1
        return counts

    # ---- Validation -------------------------------------------------

    def validate_move(self, from_row: int, from_col: int,
                      to_row: int, to_col: int) -> dict:
        """
        Kiểm tra nước đi có hợp lệ không.
        Returns dict với keys: valid(bool), reason(str), is_capture(bool),
                               captured_type(str|None), blocked(bool)
        """
        if not (0 <= to_row <= 8 and 0 <= to_col <= 8):
            return {'valid': False, 'reason': 'Ngoài bàn cờ'}

        piece = self.board[from_row][from_col] if (0 <= from_row <= 8 and 0 <= from_col <= 8) else None
        if piece is None:
            return {'valid': False, 'reason': 'Không có quân cờ tại vị trí này'}
        if piece.player != self.current_player:
            return {'valid': False, 'reason': 'Không phải quân của bạn'}

        dr = abs(to_row - from_row)
        dc = abs(to_col - from_col)
        if dr > 1 or dc > 1 or (dr == 0 and dc == 0):
            return {'valid': False, 'reason': 'Chỉ được đi 1 ô theo 8 hướng'}

        target = self.board[to_row][to_col]
        if target:
            if target.player == piece.player:
                return {'valid': False, 'reason': 'Ô đã có quân cùng phe'}
            if piece.same_type(target):
                return {'valid': False, 'reason': 'Cùng loại — bị chặn', 'blocked': True}
            if piece.beats(target):
                return {'valid': True, 'is_capture': True, 'captured_type': target.type}
            return {'valid': False, 'reason': 'Quân đối thủ khắc chế quân của bạn'}

        return {'valid': True, 'is_capture': False}

    def get_valid_moves(self, row: int, col: int) -> list[dict]:
        """
        Trả danh sách nước đi hợp lệ cho quân tại (row, col).
        Chỉ trả nước đi valid=True (không trả blocked).
        """
        moves = []
        piece = self.board[row][col] if (0 <= row <= 8 and 0 <= col <= 8) else None
        if not piece or piece.player != self.current_player:
            return moves

        for dr, dc in DIRECTIONS:
            to_row, to_col = row + dr, col + dc
            result = self.validate_move(row, col, to_row, to_col)
            if result.get('valid'):
                moves.append({
                    'from_row': row,
                    'from_col': col,
                    'to_row': to_row,
                    'to_col': to_col,
                    'is_capture': result.get('is_capture', False),
                    'captured_type': result.get('captured_type'),
                })
        return moves

    def get_all_legal_moves(self, player: Optional[int] = None) -> list[dict]:
        """
        Trả tất cả nước đi hợp lệ của player hiện tại (hoặc player chỉ định).
        """
        p = player if player is not None else self.current_player
        # Tạm thời override current_player để gọi validate_move
        original = self.current_player
        self.current_player = p
        moves = []
        for r in range(9):
            for c in range(9):
                if self.board[r][c] and self.board[r][c].player == p:
                    moves.extend(self.get_valid_moves(r, c))
        self.current_player = original
        return moves

    # ---- Execute move -----------------------------------------------

    def execute_move(self, from_row: int, from_col: int,
                     to_row: int, to_col: int) -> Optional[dict]:
        """
        Thực thi nước đi. Trả về move_record hoặc None nếu không hợp lệ.
        """
        if self.game_over:
            return None

        validation = self.validate_move(from_row, from_col, to_row, to_col)
        if not validation.get('valid'):
            return None

        piece = self.board[from_row][from_col]
        captured = self.board[to_row][to_col] if validation.get('is_capture') else None

        move_record = {
            'player': self.current_player,
            'turn_number': self.turn_number,
            'piece': piece.clone(),
            'from_row': from_row,
            'from_col': from_col,
            'to_row': to_row,
            'to_col': to_col,
            'captured': captured.clone() if captured else None,
            'is_capture': validation.get('is_capture', False),
        }

        # Thực thi
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None
        self.move_history.append(move_record)

        # Kiểm tra thắng
        self._check_win_conditions(move_record)

        if not self.game_over:
            self.current_player = 2 if self.current_player == 1 else 1
            if self.current_player == 1:
                self.turn_number += 1
            self._check_stalemate()

        return move_record

    def _check_win_conditions(self, move_record: dict):
        player = move_record['player']
        to_row = move_record['to_row']
        to_col = move_record['to_col']
        goal = GOALS[player]

        if to_row == goal['row'] and to_col == goal['col']:
            self.game_over = True
            self.winner = player
            self.win_reason = f'Player {player} đã đến đích!'
            return

        opponent = 2 if player == 1 else 1
        if any(self.count_pieces(opponent)[kind] == 0 for kind in ('rock', 'paper', 'scissors')):
            self.game_over = True
            self.winner = player
            self.win_reason = f'Player {player} đã bắt hết một loại quân đối thủ!'

    def _check_stalemate(self):
        pieces = self.get_player_pieces(self.current_player)
        for item in pieces:
            for dr, dc in DIRECTIONS:
                to_r = item['row'] + dr
                to_c = item['col'] + dc
                res = self.validate_move(item['row'], item['col'], to_r, to_c)
                if res.get('valid'):
                    return  # Còn ít nhất 1 nước đi hợp lệ

        self.game_over = True
        self.winner = 2 if self.current_player == 1 else 1
        self.win_reason = f'Player {self.current_player} hết nước đi — thua cuộc!'

    # ---- Serialization ----------------------------------------------

    def to_dict(self) -> dict:
        """Serialize trạng thái, tương đương serializeState() trong index.js."""
        board_data = []
        for r in range(9):
            row_data = []
            for c in range(9):
                p = self.board[r][c]
                row_data.append(p.to_dict() if p else None)
            board_data.append(row_data)

        last_move = None
        if self.move_history:
            m = self.move_history[-1]
            last_move = {
                'player': m['player'],
                'turn_number': m['turn_number'],
                'from_row': m['from_row'],
                'from_col': m['from_col'],
                'to_row': m['to_row'],
                'to_col': m['to_col'],
                'is_capture': m['is_capture'],
                'captured': m['captured'].to_dict() if m['captured'] else None,
            }

        return {
            'board': board_data,
            'current_player': self.current_player,
            'turn_number': self.turn_number,
            'game_over': self.game_over,
            'winner': self.winner,
            'win_reason': self.win_reason,
            'last_move': last_move,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GameState':
        """Tái tạo GameState từ dict (đã serialized)."""
        gs = cls(setup=False)
        board = data['board']
        for r in range(9):
            for c in range(9):
                cell = board[r][c]
                gs.board[r][c] = Piece.from_dict(cell) if cell else None

        gs.current_player = data.get('current_player', 1)
        gs.turn_number = data.get('turn_number', 1)
        gs.game_over = data.get('game_over', False)
        gs.winner = data.get('winner')
        gs.win_reason = data.get('win_reason', '')
        return gs

    def clone(self) -> 'GameState':
        gs = GameState(setup=False)
        gs.board = [[p.clone() if p else None for p in row] for row in self.board]
        gs.current_player = self.current_player
        gs.turn_number = self.turn_number
        gs.move_history = [dict(m) for m in self.move_history]
        gs.game_over = self.game_over
        gs.winner = self.winner
        gs.win_reason = self.win_reason
        return gs


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def build_ai_input(state: GameState) -> dict:
    """
    Xây dựng dict đầu vào cho chương trình AI.
    AI nhận JSON này qua stdin.

    Schema:
    {
        "board": [[{player, type, id} | null, ...], ...],  # 9x9
        "current_player": 1 | 2,
        "turn_number": int,
        "legal_moves": [
            {"from_row": int, "from_col": int,
             "to_row": int, "to_col": int,
             "is_capture": bool, "captured_type": str|null}
        ],
        "goal": {"row": int, "col": int},
        "opponent_goal": {"row": int, "col": int}
    }
    """
    board_data = []
    for r in range(9):
        row_data = []
        for c in range(9):
            p = state.board[r][c]
            row_data.append(p.to_dict() if p else None)
        board_data.append(row_data)

    legal_moves = state.get_all_legal_moves()
    player = state.current_player
    opponent = 2 if player == 1 else 1

    return {
        'board': board_data,
        'current_player': player,
        'turn_number': state.turn_number,
        'legal_moves': legal_moves,
        'goal': GOALS[player],
        'opponent_goal': GOALS[opponent],
        'game_over': state.game_over,
    }


def parse_ai_output(raw: str) -> Optional[dict]:
    """
    Parse output của AI.
    Trả về dict {'from_row', 'from_col', 'to_row', 'to_col'}
    hoặc None nếu parse thất bại.

    AI phải in JSON dạng:
    {"move": {"from_row": int, "from_col": int, "to_row": int, "to_col": int}}
    """
    import json

    if not raw or not raw.strip():
        return None

    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    move = data.get('move')
    if not isinstance(move, dict):
        return None

    required = ('from_row', 'from_col', 'to_row', 'to_col')
    for key in required:
        if key not in move:
            return None
        if not isinstance(move[key], int):
            try:
                move[key] = int(move[key])
            except (TypeError, ValueError):
                return None

    return {
        'from_row': move['from_row'],
        'from_col': move['from_col'],
        'to_row': move['to_row'],
        'to_col': move['to_col'],
    }


def validate_ai_move(state: GameState, move: dict) -> dict:
    """
    Xác thực nước đi của AI bằng game engine.
    Chỉ engine mới có quyền xác nhận hợp lệ.

    Returns:
        {
            'valid': bool,
            'reason': str,
            'is_capture': bool,
            'captured_type': str | None
        }
    """
    if not move:
        return {'valid': False, 'reason': 'Nước đi rỗng'}

    result = state.validate_move(
        move['from_row'], move['from_col'],
        move['to_row'], move['to_col'],
    )

    return {
        'valid': result.get('valid', False),
        'reason': result.get('reason', ''),
        'is_capture': result.get('is_capture', False),
        'captured_type': result.get('captured_type'),
    }
