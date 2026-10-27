"""
matches/consumers.py
--------------------
WebSocket consumer cho real-time match updates.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from matches.models import Match

logger = logging.getLogger(__name__)


class MatchConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.match_id = self.scope['url_route']['kwargs']['match_id']
        self.room_group_name = f'match_{self.match_id}'

        # Kiểm tra match tồn tại
        match = await self.get_match()
        if not match:
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Gửi state hiện tại ngay
        await self.send_current_state()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if data.get('type') == 'get_state':
            await self.send_current_state()
        elif data.get('type') == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def match_finished(self, event):
        """Nhận event từ background thread khi match kết thúc"""
        await self.send(text_data=json.dumps({
            'type': 'finished',
            'data': event['data']
        }))

    async def send_current_state(self):
        match = await self.get_match()
        if match:
            await self.send(text_data=json.dumps({
                'type': 'state',
                'data': {
                    'match_id': match.id,
                    'status': match.status,
                    'winner': match.winner,
                    'win_reason': match.win_reason,
                    'board_state': match.board_state,
                    'replay_data': match.replay_data,
                }
            }))

    @database_sync_to_async
    def get_match(self):
        try:
            return Match.objects.get(id=self.match_id)
        except Match.DoesNotExist:
            return None