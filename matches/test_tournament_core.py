"""Regression tests independent of Django, Docker daemon and production DB."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from .bot_runner import BotError, BotRunner, RunnerUnavailable, _reject_constant, _unique_object
from .game_engine import GameState, board_presets
from .match_manager import MatchManager
from .sample_bots import SampleBotRunner
from .tournament import freeze, load_frozen, standings, schedule, rank, run, canonical, digest, write_json


class RuleTests(unittest.TestCase):
    def capture_state(self, max_plies=300):
        state = GameState(max_plies=max_plies)
        state.pieces = [p for p in state.pieces if not (p['owner'] == 'P2' and p['type'] == 'scissors')]
        state.pieces.append({'id': 'last-scissors', 'owner': 'P2', 'type': 'scissors', 'at': [4, 1]})
        return state

    def test_last_type_wins_even_with_other_enemy_pieces(self):
        state = self.capture_state()
        move = next(m for m in state.legal_moves() if m['from'] == [3, 1] and m['to'] == [4, 1])
        self.assertTrue(move['wins_immediately'])
        state.apply_move(move)
        self.assertEqual(state.winner, 'P1')
        self.assertEqual(state.reason['code'], 'type_eliminated')
        self.assertEqual(sum(p['owner'] == 'P2' for p in state.pieces), 6)

    def test_win_has_priority_over_maximum_plies(self):
        state = self.capture_state(max_plies=1)
        state.apply_move(next(m for m in state.legal_moves() if m['to'] == [4, 1] and m['from'] == [3, 1]))
        self.assertEqual(state.result, 'win')

    def test_non_terminal_maximum_is_draw(self):
        state = GameState(max_plies=1)
        state.apply_move(state.legal_moves()[0])
        self.assertEqual(state.reason['code'], 'max_plies')

    def test_finished_game_rejects_moves(self):
        state = GameState(max_plies=1)
        state.apply_move(state.legal_moves()[0])
        with self.assertRaises(ValueError):
            state.apply_move(state.legal_moves()[0])

    def test_boolean_coordinate_is_rejected(self):
        state = GameState()
        move = state.legal_moves()[0]
        move['from'][0] = True
        with self.assertRaises(ValueError):
            state.apply_move(move)

    def test_repetition_ignores_ids_of_interchangeable_pieces(self):
        state = GameState()
        previous = state._key()
        same = [p for p in state.pieces if p['owner'] == 'P1' and p['type'] == 'rock']
        same[0]['id'], same[1]['id'] = same[1]['id'], same[0]['id']
        self.assertEqual(previous, state._key())

    def test_threefold_repetition(self):
        state = GameState()
        state.pieces = [
            {'id': f'{owner}-{kind}', 'owner': owner, 'type': kind, 'at': at}
            for owner, kind, at in [('P1', 'rock', [2, 2]), ('P1', 'paper', [1, 1]), ('P1', 'scissors', [1, 2]),
                                    ('P2', 'rock', [8, 8]), ('P2', 'paper', [9, 8]), ('P2', 'scissors', [9, 9])]]
        state.repetitions.clear()
        state._mark_position()
        for _ in range(2):
            for owner, origin, dest in [('P1', [2, 2], [3, 2]), ('P2', [8, 8], [7, 8]),
                                        ('P1', [3, 2], [2, 2]), ('P2', [7, 8], [8, 8])]:
                state.apply_move({'piece_id': owner + '-rock', 'from': origin, 'to': dest})
        self.assertEqual(state.reason['code'], 'threefold_repetition')


class RankingTests(unittest.TestCase):
    def test_double_round_robin_balanced(self):
        fixtures = schedule(['c', 'a', 'b'])
        self.assertEqual(len(fixtures), 6)
        self.assertEqual(len({f['id'] for f in fixtures}), 6)
        self.assertEqual(sum(g['p1'] == 'a' for g in fixtures), 2)
        self.assertEqual(sum(g['p2'] == 'a' for g in fixtures), 2)

    def test_points_forfeit_and_infrastructure(self):
        rows = standings(['a', 'b'], [
            {'id': '1', 'p1': 'a', 'p2': 'b', 'result': 'forfeit', 'winner': 'P1'},
            {'id': '2', 'p1': 'b', 'p2': 'a', 'result': 'draw', 'winner': None},
            {'id': '3', 'p1': 'a', 'p2': 'b', 'result': 'error', 'winner': None}])
        self.assertEqual([r['points'] for r in rows], [4, 1])
        self.assertEqual([r['played'] for r in rows], [2, 2])
        self.assertEqual(rows[0]['sonneborn_berger'], 1.5)

    def test_cycle_remains_shared_rank(self):
        games = [dict(id=str(i), p1=a, p2=b, result='win', winner='P1')
                 for i, (a, b) in enumerate([('a','b'), ('b','c'), ('c','a')])]
        self.assertEqual([r['rank'] for r in standings(['a','b','c'], games)], [1,1,1])

    def test_duplicates_fail_instead_of_double_count(self):
        game = dict(id='x', p1='a', p2='b', result='draw', winner=None)
        with self.assertRaises(ValueError):
            standings(['a','b'], [game, game])

    def test_invalid_winner_rejected(self):
        with self.assertRaises(ValueError):
            standings(['a','b'], [dict(id='x', p1='a', p2='b', result='win', winner=None)])


class RunnerTests(unittest.TestCase):
    def test_unavailable_runner_does_not_forfeit(self):
        def unavailable(*args):
            raise RunnerUnavailable('offline')
        replay = MatchManager(unavailable).run('a', 'b')
        self.assertEqual(replay['result'], 'error')
        self.assertIsNone(replay['winner'])
        self.assertEqual(replay['events'][0]['type'], 'started')

    def test_bot_fault_is_a_forfeit(self):
        class Broken:
            def __init__(self, *args): pass
            def run_turn(self, state): raise BotError('timeout', 'timeout')
        replay = MatchManager(Broken).run('a', 'b')
        self.assertEqual(replay['result'], 'forfeit')
        self.assertEqual(replay['winner'], 'P2')

    def test_no_docker_has_no_host_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'bot.py'
            source.write_text('raise RuntimeError("must never run")')
            with patch('matches.bot_runner.shutil.which', return_value=None):
                with self.assertRaises(RunnerUnavailable):
                    BotRunner(source, temp)

    def test_docker_command_has_isolation_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'bot.py'
            source.write_text('print(1)')
            with patch('matches.bot_runner.shutil.which', return_value='docker'):
                runner = BotRunner(source, temp)
            with patch.object(runner, '_control', return_value=b'') as control, patch.object(runner, '_execute', return_value=({}, {})):
                runner.run_turn({})
            args = control.call_args_list[0].args
            for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--memory=256m', '--pids-limit=32'):
                self.assertIn(flag, args)
            self.assertIn('target=/bot.py,readonly', next(x for x in args if x.startswith('type=bind,')))
            self.assertEqual(control.call_args_list[-1].args[:2], ('rm', '-f'))

    def test_json_extensions_and_duplicate_keys_rejected(self):
        for data in ('{"a":NaN}', '{"a":1,"a":2}'):
            with self.assertRaises(ValueError):
                json.loads(data, parse_constant=_reject_constant, object_pairs_hook=_unique_object)


class FrozenTournamentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('a', 'b'):
            (self.root / (name + '.py')).write_text('print("sample")', encoding='utf-8')
        entries = [dict(team_id=name, path=name+'.py') for name in ('a','b')]
        (self.root/'entries.json').write_text(json.dumps(entries))
        self.directory = self.root/'frozen'
        freeze(self.root/'entries.json', self.directory, 'sha256:'+'a'*64)

    def test_changed_source_rejected(self):
        (self.directory/'bots/a.py').write_text('print("changed")')
        with self.assertRaises(ValueError): load_frozen(self.directory)

    def test_incomplete_rank_must_be_explicitly_provisional(self):
        with self.assertRaises(ValueError): rank(self.directory)
        self.assertEqual(rank(self.directory, True)['pending_games'], 2)

    def test_resume_does_not_rerun_or_duplicate_scores(self):
        real = MatchManager(SampleBotRunner)
        with patch('matches.tournament.MatchManager', return_value=real):
            run(self.directory)
        final = rank(self.directory)
        self.assertEqual(sum(row['played'] for row in final['standings']), 4)
        with patch('matches.tournament.MatchManager') as manager:
            run(self.directory)
            manager.assert_not_called()

    def test_infrastructure_attempt_preserved_without_final_result(self):
        replay = MatchManager(lambda *args: (_ for _ in ()).throw(RunnerUnavailable())).run('a','b',match_id='g000001')
        with patch('matches.tournament.MatchManager') as manager:
            manager.return_value.run.return_value = replay
            with self.assertRaises(RuntimeError): run(self.directory)
        self.assertEqual(len(list((self.directory/'attempts').glob('*.json'))), 1)
        self.assertEqual(len(list((self.directory/'results').glob('*.json'))), 0)
        self.assertFalse((self.directory/'.running').exists())

    def test_lock_prevents_two_coordinators(self):
        (self.directory/'.running').write_text('other process')
        with self.assertRaises(FileExistsError): run(self.directory)


if __name__ == '__main__':
    unittest.main()
