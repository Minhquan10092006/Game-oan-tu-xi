import uuid
from unittest.mock import patch
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.db import OperationalError
from web.models import Season, CompetitionEntry
from .models import Submission, SubmissionReceipt


class OfflineSubmissionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('offline-player')
        self.client.force_login(self.user)
        self.season = Season.objects.create(name='Offline', start_date=timezone.localdate(),
            phase='submission', submission_deadline=timezone.now() + timedelta(days=1))
        self.entry = CompetitionEntry.objects.create(user=self.user, season=self.season, display_name='Offline')
        self.payload = {'ai_name': 'Bot', 'source_code': 'print(1)', 'competition_entry': self.entry.pk,
                        'client_submission_id': str(uuid.uuid4())}

    def send(self, payload=None):
        return self.client.post('/api/submissions/', payload or self.payload, content_type='application/json')

    @override_settings(SUBMISSION_RATE_LIMIT_PER_DAY=1)
    def test_lost_response_retry_returns_receipt_even_after_lock_and_quota(self):
        first = self.send()
        self.assertEqual(first.status_code, 201)
        self.season.phase = 'locked'
        self.season.save()
        retry = self.send()
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.json()['id'], retry.json()['id'])
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(SubmissionReceipt.objects.count(), 1)

    def test_same_key_changed_source_rejected(self):
        self.send()
        self.assertEqual(self.send({**self.payload, 'source_code': 'print(2)'}).status_code, 409)
        self.assertEqual(Submission.objects.count(), 1)

    def test_offline_timestamp_cannot_bypass_deadline(self):
        self.season.submission_deadline = timezone.now() - timedelta(seconds=1)
        self.season.save()
        self.assertEqual(self.send().status_code, 400)
        self.assertFalse(SubmissionReceipt.objects.exists())

    def test_key_scoped_to_owner_and_cannot_use_other_entry(self):
        self.send()
        other = get_user_model().objects.create_user('other-offline')
        self.client.force_login(other)
        self.assertEqual(self.send().status_code, 400)
        payload = {**self.payload, 'competition_entry': None, 'practice': True}
        response = self.send(payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SubmissionReceipt.objects.count(), 2)

    def test_session_requires_login_and_never_cached(self):
        response = self.client.get('/api/submissions/session/')
        self.assertEqual(response.json()['user_id'], self.user.pk)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.client.logout()
        self.assertIn(self.client.get('/api/submissions/session/').status_code, (401, 403))

    def test_bad_id_does_not_create_submission(self):
        self.assertEqual(self.send({**self.payload, 'client_submission_id': 'bad-id'}).status_code, 400)
        self.assertFalse(Submission.objects.exists())

    def test_account_switch_between_session_check_and_post_is_rejected(self):
        response = self.send({**self.payload, 'client_account_id': self.user.pk + 1})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Submission.objects.exists())

    def test_database_failure_does_not_consume_receipt(self):
        with self.assertLogs('config.exception_handler',level='ERROR'), patch('submissions.serializers.SubmissionCreateSerializer.create', side_effect=OperationalError('offline recovery test')):
            response = self.send()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(SubmissionReceipt.objects.exists())
        self.assertEqual(self.send().status_code, 201)

    def test_offline_shell_is_anonymous_even_when_logged_in(self):
        response = self.client.get('/ai/offline/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'offline-player')
        self.assertContains(response, 'submission-offline.js')
        worker = self.client.get('/submission-sw.js')
        self.assertEqual(worker['Service-Worker-Allowed'], '/')

    @override_settings(ALLOWED_HOSTS=['192.168.1.10'])
    def test_http_lan_submission_with_real_csrf_and_idempotent_retry(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST='192.168.1.10:8000')
        client.force_login(self.user)
        session = client.get('/api/submissions/session/').json()
        headers = {'HTTP_X_CSRFTOKEN': session['csrf_token'],
                   'HTTP_ORIGIN': 'http://192.168.1.10:8000'}
        first = client.post('/api/submissions/', self.payload, content_type='application/json', **headers)
        self.assertEqual(first.status_code, 201)
        retry = client.post('/api/submissions/', self.payload, content_type='application/json', **headers)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(first.json()['id'], retry.json()['id'])
        self.assertEqual(Submission.objects.count(), 1)
