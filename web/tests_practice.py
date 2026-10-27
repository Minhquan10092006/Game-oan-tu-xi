import hashlib
import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from matches.tournament import engine_hash
from matches.match_manager import MatchManager
from matches.sample_bots import SampleBotRunner
from submissions.models import Submission
from .models import PracticeMatch, JudgeWorker, Season, CompetitionEntry, OfficialBot, JudgingJob, TournamentFixture
from . import practice_ops


class PracticeTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('practice-owner')
        self.other=get_user_model().objects.create_user('practice-opponent')
        self.own=Submission.objects.create(submitter=self.user,ai_name='My bot',source_code='print(1)')
        self.other_bot=Submission.objects.create(submitter=self.other,ai_name='Opponent',source_code='print(2)',review_status='approved')
        self.worker=JudgeWorker.objects.create(slot=1,name='Worker',token_hash=hashlib.sha256(b'practice-test-token').hexdigest())
        self.client.force_login(self.user)
        self.payload={'request_id':str(uuid.uuid4()),'submission_id':self.own.pk,'opponent':'sample:aggressive','side':'P1'}

    def create(self,**changes):
        return self.client.post('/api/practice/matches/',{**self.payload,**changes},content_type='application/json')

    def test_history_only_lists_completed_practice_and_protects_replay(self):
        self.create()
        match = PracticeMatch.objects.get()
        match.state = 'completed'
        match.result = MatchManager(SampleBotRunner).run('aggressive', 'defensive', max_plies=3)
        match.result['bot_runs'] = [{'stderr': 'private-opponent-debug'}]
        match.finished_at = timezone.now()
        match.save()
        self.client.post('/api/matches/sample/')
        response = self.client.get('/history/')
        self.assertEqual(len(response.context['matches']), 1)
        self.assertContains(response, f'/history/practice-{match.pk}/')
        detail = self.client.get(f'/history/practice-{match.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'private-opponent-debug')
        self.client.force_login(self.other)
        self.assertEqual(len(self.client.get('/history/').context['matches']), 0)
        self.assertEqual(self.client.get(f'/history/practice-{match.pk}/').status_code, 404)

    def finish(self,match,job):
        result=MatchManager(SampleBotRunner).run('aggressive','defensive',max_plies=3,match_id=f'job-practice-{match.pk}')
        return practice_ops.update(self.worker,job['id'],job['lease_token'],result)

    def test_create_snapshot_idempotent_and_single_pending(self):
        response=self.create();self.assertEqual(response.status_code,201)
        self.assertEqual(self.create().status_code,200)
        self.assertEqual(self.create(request_id=str(uuid.uuid4())).status_code,409)
        self.assertEqual(self.create(side='P2').status_code,409)
        self.own.source_code='print(99)';self.own.save()
        self.assertEqual(PracticeMatch.objects.get().own_source,'print(1)')

    def test_cannot_use_other_users_source_or_unapproved_opponent(self):
        self.assertEqual(self.create(submission_id=self.other_bot.pk).status_code,409)
        self.other_bot.review_status='pending';self.other_bot.save()
        self.assertEqual(self.create(opponent=f'submission:{self.other_bot.pk}').status_code,409)
        self.assertFalse(PracticeMatch.objects.exists())

    def test_rejected_own_source_is_not_available(self):
        self.own.review_status='rejected';self.own.save()
        self.assertEqual(self.create().status_code,409)
        self.assertEqual(self.client.get('/api/practice/options/').json()['mine'],[])

    def test_worker_claim_heartbeat_complete_and_no_official_score(self):
        self.create(side='P2');match=PracticeMatch.objects.get()
        job=practice_ops.claim(self.worker.pk,engine_hash())
        self.assertEqual(job['id'],f'practice-{match.pk}')
        self.assertEqual(job['bots'][1]['source'],'print(1)')
        self.assertIsNone(practice_ops.claim(self.worker.pk,engine_hash()))
        practice_ops.update(self.worker,job['id'],job['lease_token'],heartbeat=True)
        result=self.finish(match,job)
        self.assertEqual(result.state,'completed')
        self.assertEqual(TournamentFixture.objects.count(),0)
        self.assertEqual(self.user.profile.elo,1200)
        with self.assertRaises(ValueError):self.finish(match,job)

    def test_expired_lease_can_move_to_another_worker(self):
        self.create();match=PracticeMatch.objects.get();job=practice_ops.claim(self.worker.pk,engine_hash())
        PracticeMatch.objects.filter(pk=match.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        other=JudgeWorker.objects.create(slot=2,name='Other worker',token_hash='a'*64)
        replacement=practice_ops.claim(other.pk,engine_hash())
        self.assertEqual(replacement['id'],job['id'])
        self.assertNotEqual(replacement['lease_token'],job['lease_token'])
        with self.assertRaises(ValueError):practice_ops.update(self.worker,job['id'],job['lease_token'],heartbeat=True)

    def test_official_jobs_get_priority(self):
        self.create()
        season=Season.objects.create(name='Priority',start_date=timezone.localdate(),phase='submission',judge_image='sha256:'+'a'*64,judge_engine=engine_hash())
        entry=CompetitionEntry.objects.create(user=self.user,season=season,display_name='Owner')
        bot=OfficialBot.objects.create(entry=entry,submission=self.own,source_code=self.own.source_code,sha256=self.own.source_sha256)
        official=JudgingJob.objects.create(season=season,kind='validation',bot=bot)
        job=practice_ops.claim(self.worker.pk,engine_hash())
        self.assertEqual(job['id'],official.pk)
        self.assertEqual(PracticeMatch.objects.get().state,'queued')
        self.assertIsNone(practice_ops.claim(self.worker.pk,engine_hash()))

    def test_private_replay_redacts_opponent_stderr_and_extra_source(self):
        self.create(opponent=f'submission:{self.other_bot.pk}');match=PracticeMatch.objects.get()
        match.state='completed';match.result={'events':[],'source_code':'private code',
            'bot_runs':[{'player':'P1','stderr':'mine'},{'player':'P2','stderr':'secret opponent source'}]};match.save()
        data=self.client.get(f'/api/practice/matches/{match.pk}/replay/').json()
        self.assertNotIn('source_code',data)
        self.assertEqual(data['bot_runs'][0]['stderr'],'mine')
        self.assertNotIn('stderr',data['bot_runs'][1])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/practice/matches/').json(),[])
        self.assertEqual(self.client.get(f'/api/practice/matches/{match.pk}/replay/').status_code,404)

    @override_settings(PRACTICE_MATCHES_PER_DAY=1)
    def test_cancel_and_daily_limit(self):
        self.create();match=PracticeMatch.objects.get()
        self.assertEqual(self.client.post(f'/api/practice/matches/{match.pk}/cancel/').status_code,200)
        self.assertEqual(self.create(request_id=str(uuid.uuid4())).status_code,409)

    def test_worker_http_protocol_supports_practice_namespace(self):
        self.create()
        self.client.logout()
        headers={'HTTP_AUTHORIZATION':'Bearer practice-test-token'}
        response=self.client.post('/api/competition/workers/claim/',{'engine':engine_hash()},content_type='application/json',**headers)
        job=response.json()['job']
        self.assertTrue(job['id'].startswith('practice-'))
        heartbeat=self.client.post('/api/competition/workers/heartbeat/',{'job_id':job['id'],'lease_token':job['lease_token']},content_type='application/json',**headers)
        self.assertEqual(heartbeat.status_code,200)
        invalid=self.client.post('/api/competition/workers/finish/',{'job_id':job['id'],'lease_token':job['lease_token']},content_type='application/json',**headers)
        self.assertEqual(invalid.status_code,409)

    def test_student_menu_and_admin_redirect(self):
        self.assertRedirects(self.client.get('/practice/'),'/play/#practice',fetch_redirect_response=False)
        self.assertContains(self.client.get('/play/'),'practice-own')
        self.assertContains(self.client.get('/'),'href="/play/"')
        self.assertNotContains(self.client.get('/'),'href="/practice/"')
        self.user.is_staff=True;self.user.save()
        self.assertRedirects(self.client.get('/practice/'),'/tournament/',fetch_redirect_response=False)
        self.assertEqual(self.create().status_code,403)

    @override_settings(LOCAL_JUDGE_AUTOSTART=True)
    def test_create_autostarts_local_runner_once_without_a_worker_token(self):
        from unittest.mock import patch
        from .local_judge import run_until_empty
        with patch('web.practice_views.threading.Thread') as thread:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.create().status_code,201)
                self.assertEqual(self.create().status_code,200)
        thread.assert_called_once_with(target=run_until_empty,daemon=True)
        thread.return_value.start.assert_called_once()
