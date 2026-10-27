"""
web/consumers.py
================
WebSocket Consumer cho chế độ chơi Multiplayer Oẳn Tù Tì 2.0.
Sử dụng Django Channels và Daphne.
"""
from __future__ import annotations

import re
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .room_manager import RoomManager, serialize_room, serialize_move, MAX_SPECTATORS

logger = logging.getLogger(__name__)


def get_group_name(code: str) -> str:
    """Tạo group name an toàn cho Channels (chỉ chứa a-zA-Z0-9_-)."""
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '', code.upper())
    return f"room_{clean}"


# ── ELO helpers (chạy trong thread pool qua database_sync_to_async) ──

@database_sync_to_async
def _do_update_elo(winner_user_id: int, loser_user_id: int):
    """Cập nhật ELO cho người thắng và người thua. Chạy trong threadpool."""
    from django.contrib.auth import get_user_model
    from web.models import update_elo_after_match
    User = get_user_model()
    try:
        winner = User.objects.get(pk=winner_user_id)
        loser  = User.objects.get(pk=loser_user_id)
        update_elo_after_match(winner, loser)
        logger.info('ELO updated: winner=%s loser=%s', winner.username, loser.username)
    except Exception as e:
        logger.warning('ELO update failed (winner_id=%s, loser_id=%s): %s',
                       winner_user_id, loser_user_id, e)


@database_sync_to_async
def _do_update_draw(user_id1: int, user_id2: int):
    """Cập nhật draws cho cả hai người khi hòa."""
    from django.contrib.auth import get_user_model
    from web.models import UserProfile
    User = get_user_model()
    try:
        for uid in (user_id1, user_id2):
            profile, _ = UserProfile.objects.get_or_create(
                user=User.objects.get(pk=uid)
            )
            profile.draws += 1
            profile.save(update_fields=['draws', 'updated_at'])
        logger.info('Draw recorded for user_ids %s, %s', user_id1, user_id2)
    except Exception as e:
        logger.warning('Draw update failed: %s', e)


@database_sync_to_async
def _do_handle_room_elo(uid1: int | None, uid2: int | None, winner: int | None):
    """
    Cập nhật ELO cho cả hai người chơi hoặc solo vs guest/bot trong phòng đấu.
    Trả về dict elo_info: { 'p1': { 'delta': int, 'elo': int }, 'p2': { ... } }
    """
    from django.contrib.auth import get_user_model
    from web.models import update_elo_after_match, update_user_elo_solo, UserProfile
    User = get_user_model()
    elo_info = {'p1': None, 'p2': None}
    try:
        u1 = User.objects.get(pk=uid1) if uid1 else None
        u2 = User.objects.get(pk=uid2) if uid2 else None

        if u1 and u2:
            if winner == 1:
                wp, lp = update_elo_after_match(u1, u2)
                elo_info['p1'] = {'delta': getattr(wp, 'delta', 16), 'elo': wp.elo}
                elo_info['p2'] = {'delta': getattr(lp, 'delta', -16), 'elo': lp.elo}
            elif winner == 2:
                wp, lp = update_elo_after_match(u2, u1)
                elo_info['p2'] = {'delta': getattr(wp, 'delta', 16), 'elo': wp.elo}
                elo_info['p1'] = {'delta': getattr(lp, 'delta', -16), 'elo': lp.elo}
            else:
                p1, _ = UserProfile.objects.get_or_create(user=u1)
                p2, _ = UserProfile.objects.get_or_create(user=u2)
                p1.draws += 1
                p1.save(update_fields=['draws', 'updated_at'])
                p2.draws += 1
                p2.save(update_fields=['draws', 'updated_at'])
                elo_info['p1'] = {'delta': 0, 'elo': p1.elo}
                elo_info['p2'] = {'delta': 0, 'elo': p2.elo}
        elif u1 and not u2:
            won = True if winner == 1 else (False if winner == 2 else None)
            prof, delta, old_elo, new_elo = update_user_elo_solo(u1, won)
            elo_info['p1'] = {'delta': delta, 'elo': new_elo}
        elif u2 and not u1:
            won = True if winner == 2 else (False if winner == 1 else None)
            prof, delta, old_elo, new_elo = update_user_elo_solo(u2, won)
            elo_info['p2'] = {'delta': delta, 'elo': new_elo}
    except Exception as e:
        logger.warning('Room ELO update error: %s', e)

    return elo_info


class MultiplayerConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_manager = RoomManager.get_instance()
        self.room_code: str | None = None
        self.player_number: int | None = None
        self.is_spectator: bool = False
        self.subscribed_groups: set[str] = set()

    def _get_scope_user(self):
        """Lấy Django user từ WebSocket scope. Trả về None nếu không xác thực."""
        user = self.scope.get('user')
        if user and user.is_authenticated:
            return user
        return None

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        if self.room_code:
            await self._handle_leave(self.room_code)

        for group in list(self.subscribed_groups):
            await self.channel_layer.group_discard(group, self.channel_name)
        self.subscribed_groups.clear()

    async def _handle_leave(self, code: str):
        group_name = get_group_name(code)
        if self.is_spectator:
            room = self.room_manager.leave_spectator(code, self.channel_name)
            if room:
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "room_event",
                        "data": {
                            "event": "spectator_count",
                            "payload": {
                                "code": code,
                                "count": len(room.spectators),
                                "max": MAX_SPECTATORS,
                            }
                        }
                    }
                )
        else:
            result = self.room_manager.leave_room(code, self.channel_name)
            if isinstance(result, dict) and result.get("deleted"):
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "room_event",
                        "data": {
                            "event": "room_deleted",
                            "payload": {"code": code}
                        }
                    }
                )
            elif result:
                room = result
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "room_event",
                        "data": {
                            "event": "room_update",
                            "payload": {
                                "code": code,
                                "names": room.names,
                                "status": room.status,
                                "state": serialize_room(room),
                                "spectatorCount": len(room.spectators),
                            }
                        }
                    }
                )

    async def receive_json(self, content):
        event = content.get('event')
        req_id = content.get('_reqId')

        if event == 'spectate':
            await self.handle_spectate(content, req_id)
        elif event == 'join_room':
            await self.handle_join_room(content, req_id)
        elif event == 'join_spectate':
            await self.handle_join_spectate(content, req_id)
        elif event == 'make_move':
            await self.handle_make_move(content, req_id)
        elif event == 'reset_room':
            await self.handle_reset_room(content, req_id)
        elif event == 'leave_room':
            await self.handle_leave_room(content, req_id)
        elif event == 'ping':
            await self.send_json({"event": "pong", "_reqId": req_id})

    async def handle_spectate(self, content, req_id):
        codes = content.get('codes', [])
        snapshot = []
        for code in codes:
            code = code.upper().strip()
            room = self.room_manager.get_room(code)
            if not room:
                room = self.room_manager.create_room(code)

            group_name = get_group_name(code)
            if group_name not in self.subscribed_groups:
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.subscribed_groups.add(group_name)

            s = serialize_room(room)
            snapshot.append(s)

        await self.send_json({
            "event": "spectate_snapshot",
            "payload": snapshot,
            "_reqId": req_id,
        })

    async def handle_join_room(self, content, req_id):
        code = (content.get('code') or '').upper().strip()
        name = (content.get('name') or '').strip() or 'Player'

        if not code:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Mã phòng không hợp lệ"})
            return

        if self.room_code and self.room_code != code:
            await self._handle_leave(self.room_code)

        # Lấy user từ scope để lưu vào room (cho ELO)
        scope_user = self._get_scope_user()
        user_id = scope_user.pk if scope_user else None

        result = self.room_manager.join_room(code, self.channel_name, name, user_id=user_id)
        if 'error' in result:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": result['error']})
            return

        self.room_code = code
        self.player_number = result['player_number']
        self.is_spectator = False

        group_name = get_group_name(code)
        if group_name not in self.subscribed_groups:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.subscribed_groups.add(group_name)

        room = result['room']
        state = serialize_room(room)

        if req_id is not None:
            await self.send_json({
                "_reqId": req_id,
                "ok": True,
                "playerNumber": self.player_number,
                "state": state,
                "names": room.names,
            })

        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "room_update",
                    "payload": {
                        "code": code,
                        "names": room.names,
                        "status": room.status,
                        "state": state,
                        "spectatorCount": len(room.spectators),
                    }
                }
            }
        )

    async def handle_join_spectate(self, content, req_id):
        code = (content.get('code') or '').upper().strip()
        name = (content.get('name') or '').strip() or 'Khán giả'

        if not code:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Mã phòng không hợp lệ"})
            return

        if self.room_code and self.room_code != code:
            await self._handle_leave(self.room_code)

        result = self.room_manager.join_spectator(code, self.channel_name, name)
        if 'error' in result:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": result['error']})
            return

        self.room_code = code
        self.player_number = None
        self.is_spectator = True

        group_name = get_group_name(code)
        if group_name not in self.subscribed_groups:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.subscribed_groups.add(group_name)

        room = result['room']
        state = serialize_room(room)

        if req_id is not None:
            await self.send_json({
                "_reqId": req_id,
                "ok": True,
                "state": state,
                "spectatorCount": len(room.spectators),
                "maxSpectators": MAX_SPECTATORS,
            })

        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "spectator_count",
                    "payload": {
                        "code": code,
                        "count": len(room.spectators),
                        "max": MAX_SPECTATORS,
                    }
                }
            }
        )

    async def handle_make_move(self, content, req_id):
        code = self.room_code
        if not code:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Bạn chưa vào phòng"})
            return

        if self.is_spectator:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Người xem không thể đi nước"})
            return

        room = self.room_manager.get_room(code)
        if not room:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Phòng không tồn tại"})
            return

        if room.state.game_over:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Ván đã kết thúc"})
            return

        if room.state.current_player != self.player_number:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Chưa đến lượt bạn"})
            return

        try:
            from_row = int(content['fromRow'])
            from_col = int(content['fromCol'])
            to_row = int(content['toRow'])
            to_col = int(content['toCol'])
        except (KeyError, ValueError, TypeError):
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Tọa độ không hợp lệ"})
            return

        move_record = room.state.execute_move(from_row, from_col, to_row, to_col)
        if not move_record:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Nước đi không hợp lệ"})
            return

        game_just_ended = room.state.game_over
        if game_just_ended:
            room.status = 'finished'

        serialized_move  = serialize_move(move_record)
        serialized_state = serialize_room(room)

        if req_id is not None:
            await self.send_json({"_reqId": req_id, "ok": True})

        group_name = get_group_name(code)
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "move_made",
                    "payload": {
                        "code": code,
                        "move": serialized_move,
                        "state": serialized_state,
                        "spectatorCount": len(room.spectators),
                    }
                }
            }
        )

        # ── Cập nhật ELO khi ván kết thúc ──────────────────────────────
        if game_just_ended:
            await self._handle_game_over_elo(room)

    async def _handle_game_over_elo(self, room):
        """
        Gọi sau khi ván kết thúc: cập nhật ELO cho người chơi và gửi thông báo tới phòng.
        """
        uid1, uid2 = room.user_ids[0], room.user_ids[1]
        winner = room.state.winner   # 1, 2, hoặc None (hòa)

        if uid1 is None and uid2 is None:
            logger.info('ELO skipped for room %s: guest only', room.code)
            return

        elo_info = await _do_handle_room_elo(uid1, uid2, winner)
        logger.info('ELO processed: room=%s winner=%s uid1=%s uid2=%s elo_info=%s',
                    room.code, winner, uid1, uid2, elo_info)

        group_name = get_group_name(room.code)
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "elo_update",
                    "payload": {
                        "code": room.code,
                        "winner": winner,
                        "elo_info": elo_info,
                    }
                }
            }
        )

    async def handle_reset_room(self, content, req_id):
        code = self.room_code
        if not code or self.is_spectator:
            return

        room = self.room_manager.reset_room(code)
        if not room:
            return

        serialized_state = serialize_room(room)
        group_name = get_group_name(code)
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "room_reset",
                    "payload": {
                        "code": code,
                        "state": serialized_state,
                        "names": room.names,
                        "spectatorCount": len(room.spectators),
                    }
                }
            }
        )

    async def handle_leave_room(self, content, req_id):
        if self.room_code:
            code = self.room_code
            self.room_code = None
            self.player_number = None
            self.is_spectator = False
            await self._handle_leave(code)
        if req_id is not None:
            await self.send_json({"_reqId": req_id, "ok": True})

    async def room_event(self, event):
        await self.send_json(event["data"])
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_manager = RoomManager.get_instance()
        self.room_code: str | None = None
        self.player_number: int | None = None
        self.is_spectator: bool = False
        self.subscribed_groups: set[str] = set()

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        if self.room_code:
            await self._handle_leave(self.room_code)

        for group in list(self.subscribed_groups):
            await self.channel_layer.group_discard(group, self.channel_name)
        self.subscribed_groups.clear()

    async def _handle_leave(self, code: str):
        group_name = get_group_name(code)
        if self.is_spectator:
            room = self.room_manager.leave_spectator(code, self.channel_name)
            if room:
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "room_event",
                        "data": {
                            "event": "spectator_count",
                            "payload": {
                                "code": code,
                                "count": len(room.spectators),
                                "max": MAX_SPECTATORS,
                            }
                        }
                    }
                )
        else:
            result = self.room_manager.leave_room(code, self.channel_name)
            if isinstance(result, dict) and result.get("deleted"):
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "room_event",
                        "data": {
                            "event": "room_deleted",
                            "payload": {"code": code}
                        }
                    }
                )
            elif result:
                room = result
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "room_event",
                        "data": {
                            "event": "room_update",
                            "payload": {
                                "code": code,
                                "names": room.names,
                                "status": room.status,
                                "state": serialize_room(room),
                                "spectatorCount": len(room.spectators),
                            }
                        }
                    }
                )

    async def receive_json(self, content):
        event = content.get('event')
        req_id = content.get('_reqId')

        if event == 'spectate':
            await self.handle_spectate(content, req_id)
        elif event == 'join_room':
            await self.handle_join_room(content, req_id)
        elif event == 'join_spectate':
            await self.handle_join_spectate(content, req_id)
        elif event == 'make_move':
            await self.handle_make_move(content, req_id)
        elif event == 'reset_room':
            await self.handle_reset_room(content, req_id)
        elif event == 'leave_room':
            await self.handle_leave_room(content, req_id)
        elif event == 'ping':
            await self.send_json({"event": "pong", "_reqId": req_id})

    async def handle_spectate(self, content, req_id):
        codes = content.get('codes', [])
        snapshot = []
        for code in codes:
            code = code.upper().strip()
            room = self.room_manager.get_room(code)
            if not room:
                room = self.room_manager.create_room(code)

            group_name = get_group_name(code)
            if group_name not in self.subscribed_groups:
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.subscribed_groups.add(group_name)

            s = serialize_room(room)
            snapshot.append(s)

        await self.send_json({
            "event": "spectate_snapshot",
            "payload": snapshot,
            "_reqId": req_id,
        })

    async def handle_join_room(self, content, req_id):
        code = (content.get('code') or '').upper().strip()
        name = (content.get('name') or '').strip() or 'Player'

        if not code:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Mã phòng không hợp lệ"})
            return

        if self.room_code and self.room_code != code:
            await self._handle_leave(self.room_code)

        result = self.room_manager.join_room(code, self.channel_name, name)
        if 'error' in result:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": result['error']})
            return

        self.room_code = code
        self.player_number = result['player_number']
        self.is_spectator = False

        group_name = get_group_name(code)
        if group_name not in self.subscribed_groups:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.subscribed_groups.add(group_name)

        room = result['room']
        state = serialize_room(room)

        if req_id is not None:
            await self.send_json({
                "_reqId": req_id,
                "ok": True,
                "playerNumber": self.player_number,
                "state": state,
                "names": room.names,
            })

        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "room_update",
                    "payload": {
                        "code": code,
                        "names": room.names,
                        "status": room.status,
                        "state": state,
                        "spectatorCount": len(room.spectators),
                    }
                }
            }
        )

    async def handle_join_spectate(self, content, req_id):
        code = (content.get('code') or '').upper().strip()
        name = (content.get('name') or '').strip() or 'Khán giả'

        if not code:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Mã phòng không hợp lệ"})
            return

        if self.room_code and self.room_code != code:
            await self._handle_leave(self.room_code)

        result = self.room_manager.join_spectator(code, self.channel_name, name)
        if 'error' in result:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": result['error']})
            return

        self.room_code = code
        self.player_number = None
        self.is_spectator = True

        group_name = get_group_name(code)
        if group_name not in self.subscribed_groups:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.subscribed_groups.add(group_name)

        room = result['room']
        state = serialize_room(room)

        if req_id is not None:
            await self.send_json({
                "_reqId": req_id,
                "ok": True,
                "state": state,
                "spectatorCount": len(room.spectators),
                "maxSpectators": MAX_SPECTATORS,
            })

        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "spectator_count",
                    "payload": {
                        "code": code,
                        "count": len(room.spectators),
                        "max": MAX_SPECTATORS,
                    }
                }
            }
        )

    async def handle_make_move(self, content, req_id):
        code = self.room_code
        if not code:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Bạn chưa vào phòng"})
            return

        if self.is_spectator:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Người xem không thể đi nước"})
            return

        room = self.room_manager.get_room(code)
        if not room:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Phòng không tồn tại"})
            return

        if room.state.game_over:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Ván đã kết thúc"})
            return

        if room.state.current_player != self.player_number:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Chưa đến lượt bạn"})
            return

        try:
            from_row = int(content['fromRow'])
            from_col = int(content['fromCol'])
            to_row = int(content['toRow'])
            to_col = int(content['toCol'])
        except (KeyError, ValueError, TypeError):
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Tọa độ không hợp lệ"})
            return

        move_record = room.state.execute_move(from_row, from_col, to_row, to_col)
        if not move_record:
            if req_id is not None:
                await self.send_json({"_reqId": req_id, "error": "Nước đi không hợp lệ"})
            return

        if room.state.game_over:
            room.status = 'finished'

        serialized_move = serialize_move(move_record)
        serialized_state = serialize_room(room)

        if req_id is not None:
            await self.send_json({"_reqId": req_id, "ok": True})

        group_name = get_group_name(code)
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "move_made",
                    "payload": {
                        "code": code,
                        "move": serialized_move,
                        "state": serialized_state,
                        "spectatorCount": len(room.spectators),
                    }
                }
            }
        )

    async def handle_reset_room(self, content, req_id):
        code = self.room_code
        if not code or self.is_spectator:
            return

        room = self.room_manager.reset_room(code)
        if not room:
            return

        serialized_state = serialize_room(room)
        group_name = get_group_name(code)
        await self.channel_layer.group_send(
            group_name,
            {
                "type": "room_event",
                "data": {
                    "event": "room_reset",
                    "payload": {
                        "code": code,
                        "state": serialized_state,
                        "names": room.names,
                        "spectatorCount": len(room.spectators),
                    }
                }
            }
        )

    async def handle_leave_room(self, content, req_id):
        if self.room_code:
            code = self.room_code
            self.room_code = None
            self.player_number = None
            self.is_spectator = False
            await self._handle_leave(code)
        if req_id is not None:
            await self.send_json({"_reqId": req_id, "ok": True})

    async def room_event(self, event):
        await self.send_json(event["data"])
