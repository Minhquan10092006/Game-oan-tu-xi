import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from .models import (
    CompetitionEntry, Season, Team, TeamMembership, TournamentFixture,
    TournamentGroup, TournamentRound,
)
from .tournament import draw_season, record_fixture_result


class CompetitionSecurityTests(TestCase):
    def setUp(self):
        self.captain = get_user_model().objects.create_user('captain', password='testing', email='captain@example.com')
        self.member = get_user_model().objects.create_user('member', password='testing', email='member@example.com')
        self.attacker = get_user_model().objects.create_user('attacker', password='testing', email='attacker@example.com')
        self.season = Season.objects.create(
            name='K71 test', start_date=timezone.localdate(), entry_mode='both',
            registration_deadline=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.captain)

    def post(self, path, data):
        return self.client.post(path, data=json.dumps(data), content_type='application/json')

    def create_team(self):
        response = self.post(f'/api/competition/seasons/{self.season.pk}/teams/', {'name': 'An toan'})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_team_code_is_not_stored_plaintext_and_join_is_season_scoped(self):
        created = self.create_team()
        team = Team.objects.get(pk=CompetitionEntry.objects.get(pk=created['id']).team_id)
        self.assertNotEqual(team.join_code_hash, created['join_code'])
        self.assertFalse(team.join_code_hash.startswith('K71-'))
        self.client.force_login(self.member)
        self.assertEqual(self.post('/api/competition/teams/join/', {'join_code': created['join_code']}).status_code, 201)
        self.assertTrue(TeamMembership.objects.filter(team=team, user=self.member).exists())
        self.assertEqual(self.post(f'/api/competition/seasons/{self.season.pk}/individual/', {}).status_code, 409)

    def test_wrong_code_does_not_disclose_team(self):
        self.create_team()
        self.client.force_login(self.attacker)
        response = self.post('/api/competition/teams/join/', {'join_code': 'K71-00000000000000000000'})
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('An toan', response.json()['error'])

    def test_only_captain_can_submit_for_team(self):
        created = self.create_team()
        self.client.force_login(self.member)
        self.assertEqual(self.post('/api/competition/teams/join/', {'join_code': created['join_code']}).status_code, 201)
        payload = {'ai_name': 'memberbot', 'source_code': 'print(1)', 'competition_entry': created['id']}
        self.assertEqual(self.post('/api/submissions/', payload).status_code, 400)
        self.client.force_login(self.attacker)
        payload['ai_name'] = 'forged'
        self.assertEqual(self.post('/api/submissions/', payload).status_code, 400)
        self.client.force_login(self.captain)
        payload['ai_name'] = 'captainbot'
        self.assertEqual(self.post('/api/submissions/', payload).status_code, 201)

    def test_git_reference_requires_immutable_safe_reference_and_keeps_source(self):
        good = {
            'ai_name': 'gitbot', 'source_code': 'print(1)', 'submission_method': 'git',
            'git_url': 'https://github.com/k71/bot', 'git_commit': 'a' * 40,
        }
        response = self.post('/api/submissions/', good)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['git_commit'], 'a' * 40)
        for url in ('file:///etc/passwd', 'https://token@github.com/k71/bot', 'https://github.com/k71/bot?token=x', 'https://evil.example/bot'):
            bad = {**good, 'ai_name': 'bad' + str(len(url)), 'git_url': url}
            self.assertEqual(self.post('/api/submissions/', bad).status_code, 400)

    def test_registration_deadline_and_csrf_are_enforced(self):
        self.season.registration_deadline = timezone.now() - timedelta(seconds=1)
        self.season.save(update_fields=['registration_deadline'])
        self.assertEqual(self.post(f'/api/competition/seasons/{self.season.pk}/teams/', {'name': 'Late team'}).status_code, 409)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.attacker)
        self.assertEqual(csrf_client.post(f'/api/competition/seasons/{self.season.pk}/teams/', data='{}', content_type='application/json').status_code, 403)

    def test_competition_registration_requires_and_saves_contact_email(self):
        player = get_user_model().objects.create_user('no_email', password='testing')
        self.client.force_login(player)
        path = f'/api/competition/seasons/{self.season.pk}/individual/'
        self.assertEqual(self.post(path, {}).status_code, 400)
        response = self.post(path, {'contact_email': 'player@example.com'})
        self.assertEqual(response.status_code, 201)
        player.refresh_from_db()
        self.assertEqual(player.email, 'player@example.com')

    def test_member_can_add_email_after_already_registering(self):
        player = get_user_model().objects.create_user('existing_entry', password='testing')
        self.client.force_login(player)

        response = self.post('/api/competition/email/', {'contact_email': 'existing@example.com'})

        self.assertEqual(response.status_code, 200)
        player.refresh_from_db()
        self.assertEqual(player.email, 'existing@example.com')

    def test_draw_with_100_entries_creates_balanced_groups_and_round64_byes(self):
        encoded_password = make_password('testing')
        players = get_user_model().objects.bulk_create([
            get_user_model()(
                username=f'player_{index}', password=encoded_password,
                email=f'player{index}@example.com',
            )
            for index in range(100)
        ])
        CompetitionEntry.objects.bulk_create([
            CompetitionEntry(season=self.season, user=player, display_name=player.username)
            for player in players
        ])
        call_command('plan_season_rounds', self.season.pk, verbosity=0)

        result = draw_season(self.season.pk)

        groups = list(TournamentGroup.objects.filter(tournament_round__season=self.season).order_by('draw_order'))
        self.assertEqual(result['group_count'], 25)
        self.assertEqual(result['qualifier_count'], 50)
        self.assertEqual(result['bracket_size'], 64)
        self.assertEqual(result['bye_count'], 14)
        self.assertEqual([group.entries.count() for group in groups], [4] * 25)
        group_round = TournamentRound.objects.get(season=self.season, stage='group')
        self.assertEqual(group_round.fixtures.count(), 300)
        self.assertEqual(group_round.status, 'active')
        round_64 = TournamentRound.objects.get(season=self.season, stage='round_of_64')
        fixtures = list(round_64.fixtures.select_related('source_group1', 'source_group2'))
        self.assertEqual(len(fixtures), 32)
        self.assertEqual(sum(fixture.result == 'bye' for fixture in fixtures), 14)
        self.assertTrue(all(
            fixture.source_group2_id is None or fixture.source_group1_id != fixture.source_group2_id
            for fixture in fixtures
        ))
        self.assertFalse(CompetitionEntry.objects.filter(season=self.season, status='registered').exists())
        self.assertEqual(self.season.__class__.objects.get(pk=self.season.pk).draw_seed, result['season'].draw_seed)
        self.assertEqual(
            self.post(f'/api/competition/seasons/{self.season.pk}/individual/', {}).status_code,
            409,
        )

    def test_group_results_seed_finalists_and_knockout_winner_advances(self):
        players = [
            get_user_model().objects.create_user(f'finalist_{index}', password='testing', email=f'f{index}@example.com')
            for index in range(4)
        ]
        CompetitionEntry.objects.bulk_create([
            CompetitionEntry(season=self.season, user=player, display_name=player.username)
            for player in players
        ])
        draw_season(self.season.pk)
        group_fixtures = list(TournamentFixture.objects.filter(
            tournament_round__season=self.season,
            group__isnull=False,
        ).order_by('match_number'))
        for fixture in group_fixtures:
            record_fixture_result(fixture.pk, 'entry1_win')

        group_round = TournamentRound.objects.get(season=self.season, stage='group')
        final_round = TournamentRound.objects.get(season=self.season, stage='final')
        self.assertEqual(group_round.status, 'completed')
        self.assertEqual(final_round.status, 'active')
        final = TournamentFixture.objects.get(tournament_round__season=self.season, tournament_round__stage='final')
        self.assertIsNotNone(final.entry1_id)
        self.assertIsNotNone(final.entry2_id)
        self.assertEqual(final.result, 'scheduled')
        record_fixture_result(final.pk, 'entry2_win')
        final.refresh_from_db()
        self.assertEqual(final.winner_id, final.entry2_id)
        final_round.refresh_from_db()
        self.assertEqual(final_round.status, 'completed')

    def test_participants_api_exposes_group_tables_and_bracket_slots(self):
        players = [
            get_user_model().objects.create_user(
                f'viewer_{index}', password='testing', email=f'viewer{index}@example.com',
            )
            for index in range(4)
        ]
        CompetitionEntry.objects.bulk_create([
            CompetitionEntry(season=self.season, user=player, display_name=player.username)
            for player in players
        ])
        draw_season(self.season.pk)

        response = self.client.get('/api/competition/me/')

        self.assertEqual(response.status_code, 200)
        season_payload = response.json()['seasons'][0]
        self.assertEqual(len(season_payload['groups']), 1)
        self.assertEqual(len(season_payload['groups'][0]['standings']), 4)
        self.assertEqual(season_payload['groups'][0]['code'], 'A')
        self.assertEqual(season_payload['bracket'][-1]['name'], 'Chung kết')
        self.assertTrue(season_payload['bracket'][0]['fixtures'][0]['entry1'])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    def test_admin_draw_sends_personalized_email_and_locks_entries(self):
        self.captain.is_staff = True
        self.captain.save(update_fields=['is_staff'])
        CompetitionEntry.objects.create(
            season=self.season, user=self.captain, display_name='Captain',
        )
        CompetitionEntry.objects.create(
            season=self.season, user=self.member, display_name='Member',
        )

        response = self.client.post(f'/season-admin/{self.season.pk}/draw/')

        self.assertRedirects(response, '/season-admin/')
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({message.to[0] for message in mail.outbox}, {
            'captain@example.com', 'member@example.com',
        })
        self.assertTrue(all('Bảng A' in message.body for message in mail.outbox))
        self.assertFalse(CompetitionEntry.objects.filter(season=self.season, status='registered').exists())
        self.assertTrue(Season.objects.get(pk=self.season.pk).drawn_at)

    def test_admin_dashboard_renders_drawn_groups_and_result_controls(self):
        self.captain.is_staff = True
        self.captain.save(update_fields=['is_staff'])
        players = [
            self.captain,
            self.member,
            self.attacker,
            get_user_model().objects.create_user('fourth', password='testing', email='fourth@example.com'),
        ]
        CompetitionEntry.objects.bulk_create([
            CompetitionEntry(season=self.season, user=player, display_name=player.username)
            for player in players
        ])
        draw_season(self.season.pk)

        response = self.client.get('/season-admin/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bốc thăm đã khóa danh sách')
        self.assertContains(response, 'Bảng A')
        self.assertContains(response, '/season-admin/fixtures/')

    def test_round_plan_is_explicit_and_not_overwritten(self):
        call_command('plan_season_rounds', self.season.pk, verbosity=0)
        self.assertEqual(TournamentRound.objects.filter(season=self.season).count(), 6)
        self.assertEqual(TournamentRound.objects.get(season=self.season, stage='final').name, 'Chung kết')
        with self.assertRaises(CommandError):
            call_command('plan_season_rounds', self.season.pk, verbosity=0)

    def test_locking_entries_blocks_team_changes_and_official_submissions(self):
        created = self.create_team()
        call_command('lock_season_entries', self.season.pk, verbosity=0)
        entry = CompetitionEntry.objects.get(pk=created['id'])
        team = entry.team
        self.assertEqual(entry.status, 'locked')
        self.assertTrue(team.is_locked)
        self.client.force_login(self.member)
        self.assertEqual(self.post('/api/competition/teams/join/', {'join_code': created['join_code']}).status_code, 409)
        self.client.force_login(self.captain)
        response = self.post('/api/submissions/', {'ai_name': 'latebot', 'source_code': 'print(1)', 'competition_entry': entry.pk})
        self.assertEqual(response.status_code, 400)
