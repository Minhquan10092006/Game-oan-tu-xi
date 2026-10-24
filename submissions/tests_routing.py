from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from web.models import Season, CompetitionEntry, OfficialBot
from .models import Submission


class SubmissionRoutingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('routing-player')
        self.client.force_login(self.user)
        self.season = Season.objects.create(name='Routing season', start_date=timezone.localdate(), phase='submission', submission_deadline=timezone.now()+timedelta(days=1))
        self.entry = CompetitionEntry.objects.create(season=self.season,user=self.user,display_name='Representative')
        self.payload = {'ai_name':'Routing bot','source_code':'print(1)'}

    def test_single_open_entry_is_selected_without_manual_id(self):
        response = self.client.post('/api/submissions/',self.payload)
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json()['competition_entry'],self.entry.pk)
        self.assertEqual(OfficialBot.objects.get(entry=self.entry).submission_id,response.json()['id'])

    def test_multiple_open_entries_require_selection(self):
        other=Season.objects.create(name='Another',start_date=timezone.localdate())
        CompetitionEntry.objects.create(season=other,user=self.user,display_name='Other')
        response=self.client.post('/api/submissions/',self.payload)
        self.assertEqual(response.status_code,400)
        self.assertEqual(Submission.objects.count(),0)

    def test_explicit_practice_does_not_attach_to_season(self):
        response=self.client.post('/api/submissions/',{**self.payload,'practice':True})
        self.assertEqual(response.status_code,201)
        self.assertIsNone(response.json()['competition_entry'])
        self.assertFalse(OfficialBot.objects.filter(entry=self.entry).exists())

    def test_submission_page_preselects_single_season(self):
        response=self.client.get('/ai/')
        self.assertEqual(response.context['selected_submission_entry'],self.entry.pk)
        self.assertContains(response,'Routing season')
        self.assertContains(response,'id="competition-entry"')
        self.assertNotContains(response,'inputmode="numeric"')
