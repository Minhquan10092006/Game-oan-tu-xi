from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import Client, TestCase
from web.models import MatchHistory


class DemoSecurityTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='owner', password='testing')
        self.other = get_user_model().objects.create_user(username='other', password='testing')
        self.client.force_login(self.owner)

    def test_upload_endpoints_never_execute_user_code(self):
        with patch('matches.demo_views.MatchManager') as manager:
            for path in ('/api/matches/demo/', '/api/matches/demo-approved/'):
                self.assertEqual(self.client.post(path).status_code, 503)
            manager.assert_not_called()

    def test_sample_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.post('/api/matches/sample/').status_code, 401)

    def test_sample_persists_and_is_not_official(self):
        response = self.client.post('/api/matches/sample/')
        self.assertEqual(response.status_code, 201)
        record = MatchHistory.objects.get(match_id=response.json()['match_id'])
        self.assertIsNone(record.season)
        self.assertEqual(record.player, self.owner)
        self.assertEqual(self.client.get(f'/api/matches/demo/{record.match_id}/').status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f'/api/matches/demo/{record.match_id}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/matches/demo/{record.match_id}/state/').status_code, 404)

    def test_csrf_enforced_on_sample_and_upload(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        for path in ('/api/matches/sample/', '/api/matches/demo/', '/api/matches/demo-approved/'):
            self.assertEqual(client.post(path).status_code, 403)

    def test_database_failure_does_not_report_success(self):
        with patch('web.models.MatchHistory.objects.create', side_effect=DatabaseError('unavailable')):
            with self.assertLogs('matches.demo_views', level='ERROR'):
                self.assertEqual(self.client.post('/api/matches/sample/').status_code, 503)

    def test_demo_page_has_sample_action_and_csrf(self):
        response = self.client.get('/battlecode/')
        self.assertContains(response, '/api/matches/sample/')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertNotContains(response, 'player1_file')
