import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from matches.match_manager import MatchManager
from matches.sample_bots import SampleBotRunner
from matches.tournament import engine_hash
from submissions.models import Submission
from .models import Season, CompetitionEntry, OfficialBot, JudgingJob, PracticeMatch, TournamentFixture
from . import practice_ops, local_judge


class LocalPracticeIntegrationTests(TransactionTestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('local-practice')
        self.submission=Submission.objects.create(submitter=self.user,ai_name='Local bot',source_code='print(1)')

    @override_settings(PRACTICE_DOCKER_IMAGE='',TOURNAMENT_DOCKER_IMAGE='ott-bot:1')
    def test_local_runner_finishes_practice_using_existing_sandbox_executor(self):
        match,_=practice_ops.create(self.user,uuid.uuid4(),self.submission.pk,'sample:first','P2')
        def execute(job):
            self.assertEqual(job['bots'][1]['source'],self.submission.source_code)
            self.assertEqual(job['image'],'ott-bot:1')
            return MatchManager(SampleBotRunner).run('aggressive','defensive',max_plies=3,match_id='job-'+job['id'])
        with patch('web.local_judge.execute',side_effect=execute):
            self.assertTrue(local_judge.run_once())
            self.assertFalse(local_judge.run_once())
        match.refresh_from_db()
        self.assertEqual(match.state,'completed')
        self.assertEqual(TournamentFixture.objects.count(),0)
        self.assertEqual(self.user.profile.elo,1200)

    def test_local_runner_still_finishes_official_validation_before_practice(self):
        practice_ops.create(self.user,uuid.uuid4(),self.submission.pk,'sample:first','P1')
        season=Season.objects.create(name='Local official',start_date=timezone.localdate(),phase='submission',
            judge_image='ott-bot:1',judge_engine=engine_hash())
        entry=CompetitionEntry.objects.create(season=season,user=self.user,display_name='Local player')
        bot=OfficialBot.objects.create(entry=entry,submission=self.submission,source_code=self.submission.source_code,sha256=self.submission.source_sha256)
        job=JudgingJob.objects.create(season=season,kind='validation',bot=bot)
        with patch('web.local_judge.execute',return_value={'valid':True}) as execute:
            self.assertTrue(local_judge.run_once())
        self.assertEqual(execute.call_args.args[0]['kind'],'validation')
        job.refresh_from_db()
        self.assertEqual(job.state,'completed')
        self.assertEqual(PracticeMatch.objects.get().state,'queued')
