"""
web/room_manager.py
===================
Quản lý phòng chơi Multiplayer trong bộ nhớ (In-Memory Room Manager)
cho Oẳn Tù Tì 2.0 trên Django Channels.
Thay thế roomManager.js của Node.js.
"""
from __future__ import annotations

import time
from typing import Optional
from matches.engine import GameState, Piece

MAX_SPECTATORS = 10


def serialize_move(m: dict) -> Optional[dict]:
    """Serialize move_record sang định dạng JSON camelCase cho frontend."""
    if not m:
        return None
    piece = m.get('piece')
    captured = m.get('captured')
    return {
        'fromRow': m.get('from_row', m.get('fromRow')),
        'fromCol': m.get('from_col', m.get('fromCol')),
        'toRow': m.get('to_row', m.get('toRow')),
        'toCol': m.get('to_col', m.get('toCol')),
        'player': m.get('player'),
        'turnNumber': m.get('turn_number', m.get('turnNumber')),
        'isCapture': m.get('is_capture', m.get('isCapture', False)),
        'captured': captured.to_dict() if hasattr(captured, 'to_dict') else (captured if isinstance(captured, dict) else None),
        'piece': piece.to_dict() if hasattr(piece, 'to_dict') else (piece if isinstance(piece, dict) else None),
    }


def serialize_room(room: Room) -> dict:
    """Serialize room sang định dạng JSON camelCase tương thích với frontend."""
    s = room.state
    board_data = []
    for r in range(9):
        row_data = []
        for c in range(9):
            p = s.board[r][c]
            row_data.append(p.to_dict() if p else None)
        board_data.append(row_data)

    last_move = None
    if s.move_history:
        last_move = serialize_move(s.move_history[-1])

    return {
        'code': room.code,
        'names': list(room.names),
        'status': room.status,
        'spectatorCount': len(room.spectators),
        'maxSpectators': MAX_SPECTATORS,
        'board': board_data,
        'currentPlayer': s.current_player,
        'turnNumber': s.turn_number,
        'gameOver': s.game_over,
        'winner': s.winner,
        'winReason': s.win_reason,
        'lastMove': last_move,
    }


class Room:
    """Đại diện cho một phòng chơi."""

    def __init__(self, code: str):
        self.code = code
        self.state = GameState()
        self.players: list[Optional[str]] = [None, None]  # [channel_name P1, channel_name P2]
        self.names: list[str] = ['Đang chờ...', 'Đang chờ...']
        self.spectators: list[dict] = []  # list of {'channel_name': str, 'name': str}
        self.status: str = 'waiting'  # 'waiting' | 'playing' | 'finished'
        self.created_at: float = time.time()

    def reset(self):
        """Khởi động lại bàn cờ mới trong phòng."""
        self.state = GameState()
        self.status = 'playing' if all(p is not None for p in self.players) else 'waiting'


class RoomManager:
    """Singleton quản lý danh sách phòng chơi."""

    _instance: Optional[RoomManager] = None

    @classmethod
    def get_instance(cls) -> RoomManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.rooms: dict[str, Room] = {}
        # Tạo sẵn 4 phòng mặc định
        for code in ['A1', 'A2', 'A3', 'A4']:
            self.create_room(code)

    def create_room(self, code: str) -> Room:
        code = code.upper().strip()
        if code in self.rooms:
            return self.rooms[code]
        room = Room(code)
        self.rooms[code] = room
        return room

    def get_room(self, code: str) -> Optional[Room]:
        if not code:
            return None
        return self.rooms.get(code.upper().strip())

    def join_room(self, code: str, channel_name: str, player_name: str) -> dict:
        code = code.upper().strip()
        room = self.get_room(code)
        if not room:
            room = self.create_room(code)

        # Reconnect nếu socket này đã ở trong phòng
        if channel_name in room.players:
            slot = room.players.index(channel_name)
            return {'room': room, 'player_number': slot + 1}

        # Tìm slot trống
        try:
            slot = room.players.index(None)
        except ValueError:
            return {'error': 'Phòng đã đầy (2/2 người chơi)'}

        room.players[slot] = channel_name
        room.names[slot] = player_name or f'Player {slot + 1}'
        if all(p is not None for p in room.players):
            room.status = 'playing'
        return {'room': room, 'player_number': slot + 1}

    def join_spectator(self, code: str, channel_name: str, spectator_name: str) -> dict:
        code = code.upper().strip()
        room = self.get_room(code)
        if not room:
            room = self.create_room(code)

        # Đã là spectator
        for s in room.spectators:
            if s['channel_name'] == channel_name:
                return {'room': room}

        if len(room.spectators) >= MAX_SPECTATORS:
            return {'error': f'Phòng đã đủ {MAX_SPECTATORS} người xem'}

        room.spectators.append({
            'channel_name': channel_name,
            'name': spectator_name or 'Khán giả',
        })
        return {'room': room}

    def leave_spectator(self, code: str, channel_name: str) -> Optional[Room]:
        code = code.upper().strip()
        room = self.get_room(code)
        if not room:
            return None
        room.spectators = [s for s in room.spectators if s['channel_name'] != channel_name]
        return room

    def leave_room(self, code: str, channel_name: str) -> Optional[dict | Room]:
        code = code.upper().strip()
        room = self.get_room(code)
        if not room:
            return None

        if channel_name in room.players:
            idx = room.players.index(channel_name)
            room.players[idx] = None
            room.names[idx] = 'Đã rời'
            room.status = 'waiting'

        room.spectators = [s for s in room.spectators if s['channel_name'] != channel_name]

        is_default = code in ('A1', 'A2', 'A3', 'A4')
        if all(p is None for p in room.players) and len(room.spectators) == 0:
            if not is_default:
                del self.rooms[code]
                return {'deleted': True, 'code': code}
            else:
                room.state = GameState()
                room.names = ['Đang chờ...', 'Đang chờ...']
                room.status = 'waiting'

        return room

    def reset_room(self, code: str) -> Optional[Room]:
        code = code.upper().strip()
        room = self.get_room(code)
        if not room:
            return None
        room.reset()
        return room
