import hashlib
import io
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail, signing
from django.core.management import call_command
from django.test import TestCase, Client
from django.utils import timezone

from submissions.models import Submission
from matches.tournament import engine_hash
from .models import (Season, CompetitionEntry, OfficialBot, JudgeWorker, JudgingJob, TournamentRound,
                     TournamentFixture, TournamentGroup, Team, TeamMembership, TournamentAudit, VerifiedContact)
from . import tournament_ops as ops

User = get_user_model()
SOURCE = "import json,sys\ns=json.load(sys.stdin)\nprint(json.dumps({'move':s['legal_moves'][0]}))\n"
IMAGE = 'sha256:' + 'a' * 64


class TournamentOpsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('operator', 'op@example.com', 'testing')
        self.user = User.objects.create_user('player', email='player@example.com', password='testing')
        self.other = User.objects.create_user('other', email='other@example.com', password='testing')
        self.season = Season.objects.create(name='Test', start_date=timezone.localdate(), judge_image=IMAGE)
        self.entry = CompetitionEntry.objects.create(season=self.season, user=self.user, display_name='Player')
        self.sub = Submission.objects.create(submitter=self.user, competition_entry=self.entry, ai_name='Bot', source_code=SOURCE)
        self.bot = ops.select_bot(self.entry.pk, self.sub, self.user)
        self.workers = []
        for slot in range(1, 5):
            token = f'worker-{slot}-secret'
            worker = JudgeWorker.objects.create(slot=slot, name=f'Worker {slot}', token_hash=hashlib.sha256(token.encode()).hexdigest())
            self.workers.append(worker)
        self.client.force_login(self.admin)

    def post(self, url, data, **headers):
        return self.client.post('/api/competition/' + url, json.dumps(data), content_type='application/json', **headers)

    def queue(self):
        ops.enqueue_validation(self.season.pk, self.admin)

    def claim(self, index=0):
        return ops.claim_job(self.workers[index].pk, engine_hash())

    def finish(self, job, result=None, index=0):
        return ops.finish_job(self.workers[index], job['id'], job['lease_token'], result or {'valid': True})

    def test_four_workers_receive_distinct_jobs_and_fifth_slot_rejected(self):
        for index in range(3):
            user = User.objects.create_user(f'extra{index}')
            entry = CompetitionEntry.objects.create(season=self.season, user=user, display_name=user.username)
            sub = Submission.objects.create(submitter=user, competition_entry=entry, ai_name='Bot', source_code=SOURCE)
            ops.select_bot(entry.pk, sub, user)
        self.queue()
        jobs = [self.claim(i) for i in range(4)]
        self.assertEqual(len({j['id'] for j in jobs}), 4)
        self.assertIsNone(self.claim())
        self.assertEqual(JudgingJob.objects.filter(state='running').count(), 4)
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            JudgeWorker.objects.create(slot=5, name='Invalid', token_hash='bad')

    def test_expired_lease_is_reassigned_and_stale_result_is_rejected(self):
        self.queue()
        old = self.claim()
        JudgingJob.objects.filter(pk=old['id']).update(lease_until=timezone.now() - timedelta(seconds=1))
        new = self.claim(1)
        self.assertEqual(old['id'], new['id'])
        self.assertNotEqual(old['lease_token'], new['lease_token'])
        with self.assertRaises(ValueError):
            self.finish(old)
        self.finish(new, index=1)
        self.assertEqual(JudgingJob.objects.get().state, 'completed')

    def test_heartbeat_extends_only_current_lease(self):
        self.queue()
        job = self.claim()
        with self.assertRaises(ValueError):
            ops.heartbeat(self.workers[1], job['id'], job['lease_token'])
        ops.heartbeat(self.workers[0], job['id'], job['lease_token'])
        self.assertGreater(JudgingJob.objects.get().lease_until, timezone.now() + timedelta(seconds=100))

    def test_failure_never_counts_as_completed_and_retry_keeps_audit(self):
        self.queue()
        job = self.claim()
        self.finish(job, {'infrastructure_error': True, 'message': 'Docker offline'})
        self.assertEqual(ops.progress(self.season)['validation']['percent'], 0)
        ops.retry_job(job['id'], self.admin, 'Docker recovered')
        self.finish(self.claim())
        self.assertEqual(ops.progress(self.season)['validation']['percent'], 100)
        self.assertEqual(TournamentAudit.objects.get(action='retry').detail['previous_result']['message'], 'Docker offline')

    def test_completed_invalid_bot_counts_as_checked_but_blocks_running(self):
        self.queue()
        self.finish(self.claim(), {'valid': False, 'message': 'invalid JSON'})
        self.assertEqual(ops.progress(self.season)['validation']['percent'], 100)
        self.season.phase = 'locked'
        self.season.drawn_at = timezone.now()
        self.season.save()
        self.entry.status = 'locked'
        self.entry.save()
        with self.assertRaises(ValueError):
            ops.transition(self.season.pk, 'running', self.admin)

    def test_pause_prevents_new_claim_but_accepts_inflight_result(self):
        self.queue()
        job = self.claim()
        Season.objects.filter(pk=self.season.pk).update(judging_paused=True)
        self.assertIsNone(self.claim(1))
        self.finish(job)

    def test_release_change_is_rejected(self):
        self.queue()
        with self.assertRaises(ValueError):
            ops.claim_job(self.workers[0].pk, 'different-engine')
        with patch('web.tournament_ops.engine_hash', return_value='new-engine'):
            with self.assertRaises(ValueError):
                ops.enqueue_validation(self.season.pk, self.admin)

    def test_worker_api_requires_token_and_does_not_use_browser_session(self):
        self.queue()
        self.assertEqual(self.post('workers/claim/', {'engine': engine_hash()}).status_code, 403)
        client = Client(enforce_csrf_checks=True)
        response = client.post('/api/competition/workers/claim/', json.dumps({'engine': engine_hash()}), content_type='application/json', HTTP_AUTHORIZATION='Bearer worker-1-secret')
        self.assertEqual(response.status_code, 200)
        self.assertIn('source', response.json()['job']['bots'][0])

    def test_only_operator_can_control_and_browser_post_requires_csrf(self):
        self.client.force_login(self.user)
        self.assertEqual(self.post(f'seasons/{self.season.pk}/operate/', {'action': 'pause'}).status_code, 403)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(f'/api/competition/seasons/{self.season.pk}/operate/', {'action': 'pause'})
        self.assertEqual(response.status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename='operate_tournament'))
        self.assertEqual(self.post(f'seasons/{self.season.pk}/operate/', {'action': 'pause'}).status_code, 200)

    def test_official_version_cannot_be_forged_or_changed_after_lock(self):
        with self.assertRaises(ValueError):
            ops.select_bot(self.entry.pk, self.sub, self.other)
        ops.transition(self.season.pk, 'submission', self.admin)
        ops.transition(self.season.pk, 'locked', self.admin)
        self.bot.refresh_from_db()
        self.assertIsNotNone(self.bot.frozen_at)
        with self.assertRaises(ValueError):
            ops.select_bot(self.entry.pk, self.sub, self.user)
        self.client.force_login(self.user)
        response = self.client.post('/api/submissions/', {'ai_name':'Late', 'source_code':SOURCE, 'competition_entry':self.entry.pk})
        self.assertEqual(response.status_code, 400)

    def test_missing_bot_prevents_locking_and_progress_is_not_100(self):
        CompetitionEntry.objects.create(season=self.season, user=self.other, display_name='Missing')
        self.queue()
        self.finish(self.claim())
        self.assertEqual(ops.progress(self.season)['validation']['percent'], 50)
        ops.transition(self.season.pk, 'submission', self.admin)
        with self.assertRaises(ValueError):
            ops.transition(self.season.pk, 'locked', self.admin)

    def test_hard_capacity_counts_representatives(self):
        self.season.max_participants = 2
        self.season.save()
        CompetitionEntry.objects.create(season=self.season,user=self.other,display_name='Other')
        newcomer = User.objects.create_user('newcomer')
        self.client.force_login(newcomer)
        self.assertEqual(ops.participant_count(self.season),2)
        self.assertEqual(self.post(f'seasons/{self.season.pk}/register/',{}).status_code,409)
        self.assertEqual(self.post('teams/join/',{}).status_code,410)
        self.assertEqual(self.post(f'seasons/{self.season.pk}/waitlist/',{}).status_code,200)

    def test_submission_deadline_is_enforced(self):
        self.season.submission_deadline = timezone.now() - timedelta(seconds=1)
        self.season.save()
        self.client.force_login(self.user)
        response = self.client.post('/api/submissions/', {'ai_name':'Late', 'source_code':SOURCE, 'competition_entry':self.entry.pk})
        self.assertEqual(response.status_code, 400)

    def test_participant_overview_never_exposes_others_source_or_job_details(self):
        self.queue()
        self.client.force_login(self.other)
        data = self.client.get(f'/api/competition/seasons/{self.season.pk}/overview/').json()
        self.assertEqual(data['jobs'], [])
        self.assertNotIn('audit', data)
        self.assertNotIn('source_code', json.dumps(data))
        self.assertNotIn('token_hash', json.dumps(data))
        self.assertEqual(len(data['workers']), 4)

    def test_dashboard_contains_fixed_accessible_progress_and_four_workers(self):
        response = self.client.get('/tournament/')
        self.assertContains(response, 'id="validation-progress"')
        self.assertContains(response, 'id="fixture-progress"')
        self.assertContains(response, 'id="ops-workers"')
        self.assertContains(response, 'id="ops-config"')
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get('/tournament/'), 'id="ops-config"')

    def test_retired_email_endpoints_do_not_change_user(self):
        self.client.force_login(self.other)
        self.assertEqual(self.post('verify-email/',{}).status_code,410)
        self.assertEqual(self.post('email/',{'contact_email':'new@example.com'}).status_code,410)
        self.other.refresh_from_db()
        self.assertEqual(self.other.email,'other@example.com')

    def setup_fixture(self, knockout=False):
        entry = CompetitionEntry.objects.create(season=self.season, user=self.other, display_name='Other')
        sub = Submission.objects.create(submitter=self.other, competition_entry=entry, ai_name='Other', source_code=SOURCE)
        otherbot = ops.select_bot(entry.pk, sub, self.other)
        self.queue()
        while job := self.claim():
            self.finish(job)
        self.season.refresh_from_db()
        self.season.phase = 'running'
        self.season.save()
        OfficialBot.objects.update(frozen_at=timezone.now())
        self.round = TournamentRound.objects.create(season=self.season, stage='final' if knockout else 'group', order=1, name='Round')
        group = None if knockout else TournamentGroup.objects.create(tournament_round=self.round, code='A')
        fixture = TournamentFixture.objects.create(tournament_round=self.round, group=group, match_number=1, entry1=self.entry, entry2=entry)
        ops.queue_matches(self.season.pk, self.admin)
        return fixture

    def test_fixture_result_is_committed_exactly_once(self):
        fixture = self.setup_fixture()
        job = self.claim()
        result = {'id':f"job-{job['id']}", 'result':'win', 'winner':'P1', 'events':[]}
        self.finish(job, result)
        fixture.refresh_from_db()
        self.assertEqual(fixture.result, 'entry1_win')
        with self.assertRaises(ValueError):
            self.finish(job, result)
        self.assertEqual(ops.progress(self.season)['fixture']['percent'], 100)

    def test_knockout_draw_waits_for_reasoned_adjudication(self):
        fixture = self.setup_fixture(knockout=True)
        job = self.claim()
        self.finish(job, {'id':f"job-{job['id']}", 'result':'draw', 'winner':None})
        self.assertEqual(JudgingJob.objects.get(pk=job['id']).state, 'review')
        fixture.refresh_from_db()
        self.assertEqual(fixture.result, 'scheduled')
        response = self.post(f"jobs/{job['id']}/adjudicate/", {'result':'entry2_win', 'reason':'Áp dụng quy tắc phân thắng thua đã công bố'})
        self.assertEqual(response.status_code, 200)
        fixture.refresh_from_db()
        self.assertEqual(fixture.result, 'entry2_win')

    def test_replay_access_is_scoped_and_appeals_are_retired(self):
        fixture=self.setup_fixture()
        third=User.objects.create_user('outsider')
        job=self.claim()
        self.client.force_login(third)
        self.assertEqual(self.client.get(f"/api/competition/jobs/{job['id']}/replay/").status_code,403)
        self.assertEqual(self.post(f'seasons/{self.season.pk}/appeals/',{}).status_code,410)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f"/api/competition/jobs/{job['id']}/replay/").status_code,200)

    def test_provision_command_keeps_existing_tokens(self):
        before = list(JudgeWorker.objects.values_list('token_hash', flat=True))
        call_command('provision_judges', stdout=io.StringIO())
        self.assertEqual(before, list(JudgeWorker.objects.values_list('token_hash', flat=True)))

    def test_self_preflight_has_quota_and_preserves_previous_report(self):
        self.client.force_login(self.user)
        for attempt in range(5):
            response = self.post(f'entries/{self.entry.pk}/preflight/', {})
            self.assertEqual(response.status_code, 200)
            self.finish(self.claim())
        self.assertEqual(self.post(f'entries/{self.entry.pk}/preflight/', {}).status_code, 429)
        self.assertEqual(TournamentAudit.objects.filter(action='previous_preflight').count(), 4)

    def test_reopen_allows_new_version_before_any_official_match(self):
        ops.transition(self.season.pk, 'submission', self.admin)
        ops.transition(self.season.pk, 'locked', self.admin)
        with self.assertRaises(ValueError):
            ops.reopen_submissions(self.season.pk, self.admin, '')
        ops.reopen_submissions(self.season.pk, self.admin, 'Cho toàn giải sửa lỗi giao thức')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, 'registered')
        ops.select_bot(self.entry.pk, self.sub, self.user)

    def test_notices_stay_on_web_and_legacy_email_sender_is_disabled(self):
        from .models import TournamentEmail
        from django.core.management.base import CommandError
        response=self.post(f'seasons/{self.season.pk}/operate/',{'action':'notice','title':'Lịch thi','body':'Bắt đầu ngày mai','email':True})
        self.assertEqual(response.status_code,200)
        self.assertEqual(TournamentEmail.objects.count(),0)
        with self.assertRaises(CommandError):
            call_command('send_tournament_emails',stdout=io.StringIO())
        self.assertEqual(len(mail.outbox),0)

    def test_csv_import_is_atomic_at_capacity_and_export_escapes_formulas(self):
        self.season.max_participants = 1
        self.season.save()
        response = self.post(f'seasons/{self.season.pk}/roster/', {'csv':'username\nother\n'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.season.entries.count(), 1)
        self.entry.display_name = '=1+1'
        self.entry.save()
        response = self.client.get(f'/api/competition/seasons/{self.season.pk}/roster/')
        self.assertIn("'=1+1", response.content.decode())

    def test_rehearsal_creates_separate_season_and_no_official_results(self):
        from django.test import override_settings
        with override_settings(DEBUG=True):
            call_command('rehearse_tournament', participants=4, image=IMAGE, stdout=io.StringIO())
        season = Season.objects.exclude(pk=self.season.pk).get()
        self.assertEqual(season.entries.count(), 4)
        self.assertEqual(season.judging_jobs.filter(state='queued').count(), 4)
        self.assertEqual(season.judging_jobs.filter(state='completed').count(), 0)

    def test_disqualified_entry_cannot_reenter_by_withdrawing(self):
        response = self.post(f'seasons/{self.season.pk}/operate/', {'action':'disqualify', 'entry_id':self.entry.pk, 'reason':'Không đủ điều kiện'})
        self.assertEqual(response.status_code, 200)
        self.client.force_login(self.user)
        self.assertEqual(self.post(f'entries/{self.entry.pk}/withdraw/', {}).status_code, 409)
        self.assertEqual(self.post(f'seasons/{self.season.pk}/register/', {}).status_code, 403)
        self.assertEqual(ops.participant_count(self.season), 0)

    def test_waitlist_promotion_is_capacity_checked_and_audited(self):
        self.client.force_login(self.other)
        self.assertEqual(self.post(f'seasons/{self.season.pk}/waitlist/', {}).status_code, 200)
        self.client.force_login(self.admin)
        response = self.post(f'seasons/{self.season.pk}/operate/', {'action':'promote', 'user_id':self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.season.entries.filter(user=self.other).exists())
        self.assertTrue(TournamentAudit.objects.filter(action='promote_waitlist').exists())

    def test_complete_tournament_automatically_queues_new_bracket_matches(self):
        from .tournament import draw_season
        for index in range(3):
            user = User.objects.create_user(f'round-player-{index}')
            entry = CompetitionEntry.objects.create(season=self.season, user=user, display_name=user.username)
            sub = Submission.objects.create(submitter=user, competition_entry=entry, ai_name='Round', source_code=SOURCE)
            ops.select_bot(entry.pk, sub, user)
        self.queue()
        while job := self.claim():
            self.finish(job)
        ops.transition(self.season.pk, 'submission', self.admin)
        ops.transition(self.season.pk, 'locked', self.admin)
        draw_season(self.season.pk)
        ops.transition(self.season.pk, 'running', self.admin)
        ops.queue_matches(self.season.pk, self.admin)
        matches = 0
        while job := self.claim():
            self.finish(job, {'id':f"job-{job['id']}", 'result':'win', 'winner':'P1'})
            matches += 1
            self.assertLess(matches, 30)
        self.assertGreater(matches, 12)
        self.assertEqual(ops.progress(self.season)['fixture']['percent'], 100)
        ops.transition(self.season.pk, 'completed', self.admin)
        self.season.refresh_from_db()
        self.assertEqual(self.season.phase, 'completed')


class LargeTournamentTests(TestCase):
    def test_4000_individual_entries_draw_and_paginated_results(self):
        from .tournament import draw_season
        users = User.objects.bulk_create([User(username=f'load-{i}', password='!') for i in range(4000)])
        season = Season.objects.create(name='4000 rehearsal', start_date=timezone.localdate())
        CompetitionEntry.objects.bulk_create([CompetitionEntry(season=season, user=user, display_name=user.username) for user in users])
        result = draw_season(season.pk)
        self.assertEqual(result['entries'], 4000)
        self.assertEqual(result['group_count'], 1000)
        self.assertEqual(ops.participant_count(season), 4000)
        self.assertEqual(TournamentFixture.objects.filter(tournament_round__season=season, group__isnull=False).count(), 12000)
        self.client.force_login(users[0])
        response = self.client.get(f'/api/competition/seasons/{season.pk}/fixtures/?page=2')
        self.assertEqual(len(response.json()['fixtures']), 50)
        self.assertGreater(response.json()['pages'], 200)
