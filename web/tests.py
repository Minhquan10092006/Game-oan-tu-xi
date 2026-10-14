"""
web/tests.py
=============
Unit tests cho hệ thống Multiplayer WebSocket trên Django Channels
và REST API phòng chơi.
"""
from django.test import TestCase, Client
from channels.testing import WebsocketCommunicator
from config.asgi import application
from web.room_manager import RoomManager


class RoomsApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_rooms_api_status(self):
        response = self.client.get('/api/rooms/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        codes = [r['code'] for r in data]
        self.assertIn('A1', codes)
        self.assertIn('A2', codes)


class MultiplayerWebSocketTests(TestCase):
    def setUp(self):
        # Reset room manager
        self.room_manager = RoomManager.get_instance()
        self.room_manager.rooms.clear()
        for code in ['A1', 'A2', 'A3', 'A4']:
            self.room_manager.create_room(code)

    async def test_connect_and_spectate(self):
        communicator = WebsocketCommunicator(application, "/ws/multiplayer/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await communicator.send_json_to({
            "event": "spectate",
            "codes": ["A1", "A2"],
            "_reqId": 100,
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response.get("event"), "spectate_snapshot")
        rooms = response.get("payload", [])
        self.assertEqual(len(rooms), 2)
        self.assertEqual(rooms[0]["code"], "A1")
        self.assertEqual(rooms[1]["code"], "A2")

        await communicator.disconnect()

    async def test_join_room_and_make_move(self):
        # Client 1: Player 1
        c1 = WebsocketCommunicator(application, "/ws/multiplayer/")
        connected1, _ = await c1.connect()
        self.assertTrue(connected1)

        await c1.send_json_to({
            "event": "join_room",
            "code": "M1",
            "name": "Alice",
            "_reqId": 1,
        })
        res1 = await c1.receive_json_from()
        self.assertTrue(res1.get("ok"))
        self.assertEqual(res1.get("playerNumber"), 1)
        self.assertEqual(res1.get("_reqId"), 1)

        # c1 cũng nhận broadcast room_update
        update1 = await c1.receive_json_from()
        self.assertEqual(update1.get("event"), "room_update")

        # Client 2: Player 2
        c2 = WebsocketCommunicator(application, "/ws/multiplayer/")
        connected2, _ = await c2.connect()
        self.assertTrue(connected2)

        await c2.send_json_to({
            "event": "join_room",
            "code": "M1",
            "name": "Bob",
            "_reqId": 2,
        })
        res2 = await c2.receive_json_from()
        self.assertTrue(res2.get("ok"))
        self.assertEqual(res2.get("playerNumber"), 2)

        # Cả c1 và c2 đều nhận broadcast khi Player 2 vào
        update_p1 = await c1.receive_json_from()
        self.assertEqual(update_p1.get("event"), "room_update")
        self.assertEqual(update_p1.get("payload", {}).get("status"), "playing")

        update_p2 = await c2.receive_json_from()
        self.assertEqual(update_p2.get("event"), "room_update")

        # P1 đi nước đầu tiên (from 2,0 to 3,0)
        await c1.send_json_to({
            "event": "make_move",
            "fromRow": 2,
            "fromCol": 0,
            "toRow": 3,
            "toCol": 0,
            "_reqId": 3,
        })
        move_res = await c1.receive_json_from()
        self.assertTrue(move_res.get("ok"))

        # Cả 2 nhận event move_made
        move_p1 = await c1.receive_json_from()
        self.assertEqual(move_p1.get("event"), "move_made")
        self.assertEqual(move_p1.get("payload", {}).get("code"), "M1")
        self.assertEqual(move_p1.get("payload", {}).get("move", {}).get("fromRow"), 2)
        self.assertEqual(move_p1.get("payload", {}).get("move", {}).get("toRow"), 3)

        move_p2 = await c2.receive_json_from()
        self.assertEqual(move_p2.get("event"), "move_made")

        # P1 cố tình đi tiếp khi chưa tới lượt -> báo lỗi
        await c1.send_json_to({
            "event": "make_move",
            "fromRow": 3,
            "fromCol": 0,
            "toRow": 4,
            "toCol": 0,
            "_reqId": 4,
        })
        err_res = await c1.receive_json_from()
        self.assertIn("error", err_res)
        self.assertEqual(err_res.get("error"), "Chưa đến lượt bạn")

        await c1.disconnect()
        await c2.disconnect()

    async def test_spectator_cannot_move(self):
        c = WebsocketCommunicator(application, "/ws/multiplayer/")
        connected, _ = await c.connect()
        self.assertTrue(connected)

        await c.send_json_to({
            "event": "join_spectate",
            "code": "M2",
            "name": "Viewer",
            "_reqId": 1,
        })
        res = await c.receive_json_from()
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("spectatorCount"), 1)

        # Nhận broadcast spectator_count
        spec_event = await c.receive_json_from()
        self.assertEqual(spec_event.get("event"), "spectator_count")

        # Spectator thử đi nước cờ -> lỗi
        await c.send_json_to({
            "event": "make_move",
            "fromRow": 2,
            "fromCol": 0,
            "toRow": 3,
            "toCol": 0,
            "_reqId": 2,
        })
        res_move = await c.receive_json_from()
        self.assertEqual(res_move.get("error"), "Người xem không thể đi nước")

        await c.disconnect()

    async def test_leave_room(self):
        c = WebsocketCommunicator(application, "/ws/multiplayer/")
        connected, _ = await c.connect()
        self.assertTrue(connected)

        await c.send_json_to({
            "event": "join_room",
            "code": "M3",
            "name": "Leaver",
            "_reqId": 1,
        })
        res = await c.receive_json_from()
        self.assertTrue(res.get("ok"))
        _ = await c.receive_json_from()  # room_update broadcast

        # Rời phòng
        await c.send_json_to({
            "event": "leave_room",
            "_reqId": 2,
        })
        leave_res = await c.receive_json_from()
        self.assertTrue(leave_res.get("ok"))

        await c.disconnect()



class EloModelTests(TestCase):
    """Test logic ELO trong web/models.py."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user1 = User.objects.create_user(username='elo_p1', password='pass')
        self.user2 = User.objects.create_user(username='elo_p2', password='pass')

    def test_calculate_elo_equal_players(self):
        """Hai người cùng ELO 1200: thắng được +16."""
        from web.models import calculate_elo
        new_w, new_l = calculate_elo(1200, 1200)
        self.assertEqual(new_w, 1216)
        self.assertEqual(new_l, 1184)

    def test_calculate_elo_higher_wins_less(self):
        """Người ELO cao thắng người ELO thấp được ít hơn."""
        from web.models import calculate_elo
        new_w, new_l = calculate_elo(1600, 1200)
        # Delta phải nhỏ hơn 16 (ưu thế lớn)
        self.assertLess(new_w - 1600, 16)
        self.assertGreater(new_w, 1600)

    def test_calculate_elo_lower_wins_more(self):
        """Người ELO thấp thắng người ELO cao được nhiều hơn."""
        from web.models import calculate_elo
        new_w, new_l = calculate_elo(1200, 1600)
        # Delta phải lớn hơn 16 (upset)
        self.assertGreater(new_w - 1200, 16)

    def test_update_elo_after_match_updates_profiles(self):
        """update_elo_after_match tăng wins/elo winner, tăng losses/giảm elo loser."""
        from web.models import update_elo_after_match, UserProfile
        w_profile, l_profile = update_elo_after_match(self.user1, self.user2)

        self.assertGreater(w_profile.elo, 1200)
        self.assertLess(l_profile.elo, 1200)
        self.assertEqual(w_profile.wins, 1)
        self.assertEqual(l_profile.losses, 1)

    def test_userprofile_auto_created(self):
        """UserProfile được tự động tạo khi tạo user mới."""
        from web.models import UserProfile
        self.assertTrue(UserProfile.objects.filter(user=self.user1).exists())

    def test_win_rate_zero_games(self):
        """win_rate = 0 khi chưa có trận nào."""
        from web.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user1)
        self.assertEqual(profile.win_rate, 0.0)
        self.assertEqual(profile.total_games, 0)

    def test_ranking_api_returns_sorted_elo(self):
        """GET /api/ranking/ trả danh sách sắp xếp ELO giảm dần."""
        from web.models import UserProfile
        # user1 ELO 1500, user2 ELO 1100
        p1, _ = UserProfile.objects.get_or_create(user=self.user1)
        p1.elo = 1500
        p1.save()
        p2, _ = UserProfile.objects.get_or_create(user=self.user2)
        p2.elo = 1100
        p2.save()

        client = Client()
        resp = client.get('/api/ranking/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Tìm user1 và user2 trong kết quả
        names = [d['username'] for d in data]
        self.assertIn('elo_p1', names)
        self.assertIn('elo_p2', names)
        # user1 phải đứng trước user2 (ELO cao hơn)
        idx1 = names.index('elo_p1')
        idx2 = names.index('elo_p2')
        self.assertLess(idx1, idx2)

    def test_room_manager_stores_user_id(self):
        """join_room với user_id lưu đúng vào room.user_ids."""
        from web.room_manager import RoomManager
        rm = RoomManager()
        result = rm.join_room('TEST1', 'ch_name_1', 'Alice', user_id=self.user1.pk)
        self.assertNotIn('error', result)
        room = result['room']
        self.assertEqual(room.user_ids[0], self.user1.pk)
        self.assertIsNone(room.user_ids[1])

    def test_room_manager_leave_clears_user_id(self):
        """leave_room xóa user_id khỏi slot."""
        from web.room_manager import RoomManager
        rm = RoomManager()
        rm.join_room('TEST2', 'ch_x', 'Alice', user_id=self.user1.pk)
        rm.leave_room('TEST2', 'ch_x')
        room = rm.get_room('TEST2')
        if room:  # phòng không mặc định có thể bị xóa khi trống
            self.assertIsNone(room.user_ids[0])
