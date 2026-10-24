"""Admission and ownership for the one-representative competition model."""
import json
from datetime import timedelta
from importlib import import_module
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from submissions.models import Submission
from .models import Season, CompetitionEntry, Team, TeamMembership, OfficialBot, TournamentRound, TournamentFixture
from .tournament_ops import transition

User=get_user_model()


class CompetitionSecurityTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('representative',password='testing')
        self.other=User.objects.create_user('other',password='testing')
        self.admin=User.objects.create_superuser('organizer','admin@example.com','testing')
        self.season=Season.objects.create(name='New flow',start_date=timezone.localdate(),entry_mode='team',
            require_verified_email=True,registration_deadline=timezone.now()+timedelta(days=1))
        self.client.force_login(self.user)

    def post(self,path,data=None):
        return self.client.post('/api/competition/'+path,json.dumps(data or {}),content_type='application/json')

    def register(self,data=None):
        return self.post(f'seasons/{self.season.pk}/register/',data)

    def test_representative_registers_without_email_or_team_despite_legacy_flags(self):
        response=self.register({'display_name':'Nhóm thuật toán'})
        self.assertEqual(response.status_code,201)
        entry=CompetitionEntry.objects.get(pk=response.json()['id'])
        self.assertEqual(entry.user,self.user)
        self.assertIsNone(entry.team_id)
        self.assertEqual(entry.display_name,'Nhóm thuật toán')
        self.assertEqual(TeamMembership.objects.count(),0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email,'')

    def test_repeated_registration_is_idempotent(self):
        first=self.register().json()
        second=self.register()
        self.assertEqual(second.status_code,200)
        self.assertEqual(first['id'],second.json()['id'])
        self.assertEqual(self.season.entries.count(),1)

    def test_registration_remains_open_during_submission_before_deadline(self):
        self.season.phase='submission';self.season.save()
        self.assertEqual(self.register().status_code,201)

    def test_deadline_lock_and_draw_close_registration(self):
        self.season.registration_deadline=timezone.now()-timedelta(seconds=1);self.season.save()
        self.assertEqual(self.register().status_code,409)
        self.season.registration_deadline=timezone.now()+timedelta(days=1);self.season.phase='locked';self.season.save()
        self.assertEqual(self.register().status_code,409)
        self.season.phase='submission';self.season.drawn_at=timezone.now();self.season.save()
        self.assertEqual(self.register().status_code,409)

    def test_only_representative_can_submit_for_entry(self):
        entry=self.register().json()['id']
        self.client.force_login(self.other)
        payload={'ai_name':'Forged','source_code':'print(1)','competition_entry':entry}
        self.assertEqual(self.client.post('/api/submissions/',payload).status_code,400)
        self.client.force_login(self.user)
        payload['ai_name']='Own'
        self.assertEqual(self.client.post('/api/submissions/',payload).status_code,201)

    def test_guest_admin_and_csrf_cannot_register(self):
        session=self.client.session;session['is_guest']=True;session.save()
        self.assertEqual(self.register().status_code,403)
        self.client.logout();self.client.force_login(self.admin)
        self.assertEqual(self.register().status_code,403)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.user)
        self.assertEqual(csrf.post(f'/api/competition/seasons/{self.season.pk}/register/',{},content_type='application/json').status_code,403)

    def test_admin_cannot_submit_a_bot(self):
        self.client.force_login(self.admin)
        response=self.client.post('/api/submissions/',{'ai_name':'Not participant','source_code':'print(1)'})
        self.assertEqual(response.status_code,403)

    def test_public_registration_screen_has_one_path(self):
        page=self.client.get('/competition/')
        self.assertContains(page,'tài khoản')
        for marker in ('create-team-form','join-team-form','contact-email-form','name="entry_mode"'):
            self.assertNotContains(page,marker)

    def test_admin_only_sees_management_navigation(self):
        self.client.force_login(self.admin)
        page=self.client.get('/tournament/')
        for label in ('Mùa giải','Bài nộp','Chấm bài','Lịch sử đấu'):
            self.assertContains(page,label)
        for marker in ('href="/ai/"','href="/competition/"','name="entry_mode"','name="require_verified_email"','id="ops-appeal"','id="ops-profile"'):
            self.assertNotContains(page,marker)
        self.assertRedirects(self.client.get('/'),'/tournament/')
        self.assertRedirects(self.client.get('/ai/'),'/admin/code-review/')
        self.assertRedirects(self.client.get('/competition/'),'/tournament/')
        self.assertEqual(self.client.get('/admin/code-review/').status_code,200)

    def test_admin_login_opens_management_instead_of_arena(self):
        self.client.logout()
        response=self.client.post('/login/',{'action':'login','username':'organizer','password':'testing'})
        self.assertRedirects(response,'/tournament/')

    def test_registration_payload_does_not_expose_obsolete_settings(self):
        self.register()
        data=self.client.get('/api/competition/me/').json()
        self.assertNotIn('contact_email',data)
        self.assertNotIn('entry_mode',data['seasons'][0])
        overview=self.client.get(f'/api/competition/seasons/{self.season.pk}/overview/').json()
        for field in ('appeals','appeal_deadline','require_verified_email','contact_email','verified_email'):
            self.assertNotIn(field,overview)

    def test_old_team_entries_migrate_to_captain_without_changing_references(self):
        team=Team.objects.create(season=self.season,name='Historical group',captain=self.user,join_code_hash='a'*64)
        entry=CompetitionEntry.objects.create(season=self.season,team=team,display_name=team.name)
        sub=Submission.objects.create(submitter=self.user,competition_entry=entry,ai_name='Old bot',source_code='print(1)')
        OfficialBot.objects.create(entry=entry,submission=sub,source_code=sub.source_code,sha256=sub.source_sha256)
        self.season.phase='appeals';self.season.save()
        migration=import_module('web.migrations.0013_representative_entries')
        migration.convert_entries(apps,None)
        entry.refresh_from_db();sub.refresh_from_db();self.season.refresh_from_db()
        self.assertEqual(entry.user_id,self.user.pk)
        self.assertIsNone(entry.team_id)
        self.assertEqual(sub.competition_entry_id,entry.pk)
        self.assertEqual(entry.official_bot.submission_id,sub.pk)
        self.assertEqual(self.season.phase,'running')
        self.assertTrue(Team.objects.filter(pk=team.pk).exists())

    def test_completion_no_longer_requires_appeal_phase_or_deadline(self):
        self.season.phase='running';self.season.appeal_deadline=timezone.now()+timedelta(days=30);self.season.save()
        transition(self.season.pk,'completed',self.admin)
        self.season.refresh_from_db()
        self.assertEqual(self.season.phase,'completed')
