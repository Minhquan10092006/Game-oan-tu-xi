from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from .models import Season, CompetitionEntry
from .tournament import draw_season


class PlayerPositionTests(TestCase):
    def setUp(self):
        self.season=Season.objects.create(name='Position',start_date=timezone.localdate())
        self.entries=[]
        for number in range(4):
            user=get_user_model().objects.create_user(f'position-{number}')
            self.entries.append(CompetitionEntry.objects.create(user=user,season=self.season,display_name='Same name'))
        draw_season(self.season.pk)
        self.client.force_login(self.entries[0].user)

    def test_own_group_and_matches_resolved_by_id_despite_duplicate_names(self):
        data=self.client.get('/api/competition/me/').json()
        self.assertEqual(len(data['entries']),1)
        mine=data['entries'][0]
        self.assertEqual(mine['id'],self.entries[0].pk)
        position=mine['position']
        self.assertEqual(position['group'],'A')
        self.assertEqual(len(position['fixtures']),6)
        self.assertEqual(len(position['standings']),4)
        self.assertEqual(sum(row['entry_id']==mine['id'] for row in position['standings']),1)
        self.assertTrue(all(mine['id'] in (f['entry1_id'],f['entry2_id']) for f in position['fixtures']))
        self.assertEqual(position['played'],0)

    def test_dashboard_prefers_registered_season_and_exposes_position_panel(self):
        response=self.client.get('/tournament/')
        self.assertEqual(response.context['preferred_season_id'],self.season.pk)
        self.assertContains(response,'id="my-tournament-position"')

    def test_not_registered_has_no_other_players_private_position(self):
        user=get_user_model().objects.create_user('position-outsider')
        self.client.force_login(user)
        data=self.client.get('/api/competition/me/').json()
        self.assertEqual(data['entries'],[])
        self.assertEqual(len(data['seasons'][0]['groups'][0]['standings']),4)

    def test_draw_endpoint_contains_real_fixture_ids_and_graph_edges(self):
        response=self.client.get(f'/api/competition/seasons/{self.season.pk}/draw/')
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['entry']['id'],self.entries[0].pk)
        fixture=data['season']['bracket'][0]['fixtures'][0]
        for key in ['id','winner_to_id','winner_to_slot','entry1_id','entry2_id','job_id','job_state']:
            self.assertIn(key,fixture)

    def test_final_placeholders_use_the_correct_incoming_slot(self):
        from .models import TournamentRound, TournamentFixture
        from .competition_views import _fixture_payload
        semi=TournamentRound.objects.create(season=self.season,name='Bán kết thử',stage='semifinal',order=20)
        final_round=TournamentRound.objects.create(season=self.season,name='Chung kết thử',stage='final',order=21)
        final=TournamentFixture.objects.create(tournament_round=final_round,match_number=1)
        for number,slot in [(1,'entry1'),(2,'entry2')]:
            TournamentFixture.objects.create(tournament_round=semi,match_number=number,winner_to=final,winner_to_slot=slot)
        payload=_fixture_payload(final)
        self.assertIn('trận 1',payload['entry1'])
        self.assertIn('trận 2',payload['entry2'])
