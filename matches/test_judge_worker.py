import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .judge_worker import Coordinator, execute, validate_bot
from .bot_runner import BotError, RunnerUnavailable


class WorkerExecutionTests(unittest.TestCase):
    def test_remote_plain_http_and_embedded_credentials_are_rejected(self):
        for url in ('http://example.org', 'https://user:password@example.org', 'file:///tmp/a', 'https://example.org/?token=secret'):
            with self.assertRaises(ValueError):
                Coordinator(url, 'token')
        Coordinator('http://127.0.0.1:8000', 'token')
        Coordinator('https://example.org', 'token')

    def test_smoke_validation_covers_both_sides_of_all_presets(self):
        states = []
        class FakeRunner:
            def __init__(self, *args):
                pass

            def run_turn(self, state):
                states.append(state)
                return {'move': state['legal_moves'][0]}, {}
        with patch('matches.judge_worker.BotRunner', FakeRunner):
            result = validate_bot(Path('unused.py'))
        self.assertTrue(result['valid'])
        self.assertEqual(len(states), 8)
        self.assertEqual({state['current_player'] for state in states}, {'P1', 'P2'})

    def test_source_tampering_is_infrastructure_failure(self):
        job = {'image':'sha256:'+'a'*64, 'kind':'validation', 'bots':[{'source':'print(1)', 'sha256':'0'*64}]}
        with self.assertRaises(RunnerUnavailable):
            execute(job)

    def test_invalid_bot_is_distinct_from_broken_docker(self):
        source = 'print(1)'
        job = {'image':'sha256:'+'a'*64, 'kind':'validation', 'bots':[{'source':source, 'sha256':hashlib.sha256(source.encode()).hexdigest()}]}
        with patch('matches.judge_worker.validate_bot', side_effect=BotError('invalid_json', 'Không phải JSON')):
            self.assertFalse(execute(job)['valid'])
        with patch('matches.judge_worker.validate_bot', side_effect=RunnerUnavailable('No Docker')):
            with self.assertRaises(RunnerUnavailable):
                execute(job)


if __name__ == '__main__':
    unittest.main()
