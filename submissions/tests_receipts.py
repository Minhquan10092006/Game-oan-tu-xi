import hashlib
import json
from pathlib import Path
import tempfile
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from .models import Submission


class SubmissionReceiptTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='student', password='testing')
        self.client.force_login(self.user)

    def test_preserves_source_and_returns_hash(self):
        source = '\nprint("hello")\n\n'
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get('/ai/')
        response = client.post('/api/submissions/', {'ai_name': 'bot', 'source_code': source},
                               HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['source_code'], source)
        self.assertEqual(response.json()['source_sha256'], hashlib.sha256(source.encode()).hexdigest())

    @override_settings(SUBMISSION_RATE_LIMIT_PER_DAY=1)
    def test_submission_quota_is_enforced(self):
        data = {'ai_name': 'bot', 'source_code': 'print(1)'}
        self.assertEqual(self.client.post('/api/submissions/', data).status_code, 201)
        self.assertEqual(self.client.post('/api/submissions/', data).status_code, 400)
        self.assertEqual(Submission.objects.count(), 1)

    def test_guest_cannot_submit(self):
        session = self.client.session
        session['is_guest'] = True
        session.save()
        self.assertEqual(self.client.post('/api/submissions/', {'ai_name':'bot', 'source_code':'print(1)'}).status_code, 403)

    def test_export_exact_bytes_and_protects_used_submission(self):
        subs = [Submission.objects.create(submitter=self.user, ai_name=str(i), source_code='print(1)\n', review_status='approved') for i in range(2)]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            selection = root/'selection.json'
            selection.write_text(json.dumps([dict(team_id=f't{i}', submission_id=sub.pk) for i,sub in enumerate(subs)]))
            call_command('export_competition_entries', str(selection), str(root/'export'), verbosity=0)
            self.assertEqual((root/'export/t0.py').read_bytes(), b'print(1)\n')
            receipts = json.loads((root/'export/receipts.json').read_text())
            self.assertEqual(receipts[0]['source_sha256'], subs[0].source_sha256)
            with self.assertRaises(CommandError):
                call_command('export_competition_entries', str(selection), str(root/'export'))
        subs[0].refresh_from_db()
        self.assertTrue(subs[0].used_in_battle)
        self.user.is_staff = True
        self.user.save()
        self.assertEqual(self.client.delete(f'/api/submissions/admin/{subs[0].pk}/delete/').status_code, 409)
