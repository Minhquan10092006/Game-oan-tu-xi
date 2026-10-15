"""
judge/tests.py
--------------
Test Judge0 client với mock HTTP.
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings

from judge.client import Judge0Client, Judge0Error, Judge0Unavailable, Judge0RateLimited


@override_settings(
    JUDGE0_BASE_URL='https://mock-judge0.test',
    JUDGE0_API_KEY='',
    JUDGE0_CPU_TIME_LIMIT=2,
    JUDGE0_WALL_TIME_LIMIT=5,
    JUDGE0_MEMORY_LIMIT=131072,
    JUDGE0_REQUEST_TIMEOUT=10,
    JUDGE0_POLL_MAX_RETRIES=3,
    JUDGE0_POLL_INTERVAL=0.01,
)
class TestJudge0Client(TestCase):

    def _make_client(self):
        return Judge0Client()

    @patch('requests.Session.get')
    def test_get_languages(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {'id': 71, 'name': 'Python (3.8.1)'},
                {'id': 70, 'name': 'Python (2.7.17)'},
            ],
        )
        client = self._make_client()
        langs = client.get_languages()
        self.assertEqual(len(langs), 2)

    @patch('requests.Session.get')
    def test_get_python3_language_id(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {'id': 71, 'name': 'Python (3.8.1)'},
                {'id': 70, 'name': 'Python (2.7.17)'},
            ],
        )
        client = self._make_client()
        lang_id = client.get_python3_language_id()
        self.assertEqual(lang_id, 71)

    @patch('requests.Session.get')
    def test_get_python3_not_found_raises(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{'id': 1, 'name': 'C (GCC 9.2.0)'}],
        )
        client = self._make_client()
        with self.assertRaises(Judge0Error):
            client.get_python3_language_id()

    @patch('requests.Session.post')
    def test_submit_returns_token(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {'token': 'abc123'},
        )
        client = self._make_client()
        token = client.submit('print("hi")', '', 71)
        self.assertEqual(token, 'abc123')

    @patch('requests.Session.post')
    def test_submit_422_retries_without_limits(self, mock_post):
        """422 → retry không có limits."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            m = MagicMock()
            if call_count[0] == 1:
                m.status_code = 422
                m.json = lambda: {}
                m.text = 'Unprocessable'
                m.raise_for_status = MagicMock()
            else:
                m.status_code = 201
                m.json = lambda: {'token': 'retry-token'}
                m.raise_for_status = MagicMock()
            return m

        mock_post.side_effect = side_effect
        client = self._make_client()
        token = client.submit('print("hi")', '', 71)
        self.assertEqual(token, 'retry-token')
        self.assertEqual(call_count[0], 2)

    @patch('requests.Session.post')
    def test_submit_no_token_raises(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {'message': 'no token here'},
        )
        client = self._make_client()
        with self.assertRaises(Judge0Error):
            client.submit('print("hi")', '', 71)

    @patch('requests.Session.get')
    def test_get_result_accepted(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                'status': {'id': 3, 'description': 'Accepted'},
                'stdout': 'Hello\n',
                'stderr': '',
                'compile_output': '',
                'time': '0.123',
                'wall_time': '0.200',
                'memory': 4096,
                'exit_code': 0,
            },
        )
        client = self._make_client()
        result = client.get_result('abc123')
        self.assertTrue(result.is_accepted)
        self.assertEqual(result.stdout, 'Hello\n')

    @patch('requests.Session.get')
    def test_poll_result_waits_for_non_pending(self, mock_get):
        """Poll trả pending 2 lần, rồi accepted."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            m = MagicMock()
            m.status_code = 200
            m.raise_for_status = MagicMock()
            if call_count[0] <= 2:
                m.json = lambda: {
                    'status': {'id': 1, 'description': 'In Queue'},
                    'stdout': None, 'stderr': None, 'compile_output': None,
                }
            else:
                m.json = lambda: {
                    'status': {'id': 3, 'description': 'Accepted'},
                    'stdout': 'done', 'stderr': None,
                    'compile_output': None, 'time': '0.1',
                }
            return m

        mock_get.side_effect = side_effect
        client = self._make_client()
        result = client.poll_result('tok123')
        self.assertTrue(result.is_accepted)
        self.assertGreater(call_count[0], 2)

    @patch('requests.Session.get')
    def test_poll_max_retries_exceeded_raises(self, mock_get):
        """Luôn pending → raises Unavailable."""
        m = MagicMock()
        m.status_code = 200
        m.raise_for_status = MagicMock()
        m.json = lambda: {
            'status': {'id': 1, 'description': 'In Queue'},
            'stdout': None, 'stderr': None, 'compile_output': None,
        }
        mock_get.return_value = m
        client = self._make_client()
        with self.assertRaises(Judge0Unavailable):
            client.poll_result('tok-timeout')

    @patch('requests.Session.get')
    def test_429_raises_rate_limited(self, mock_get):
        import requests as req_lib
        m = MagicMock()
        m.status_code = 429
        m.raise_for_status.side_effect = req_lib.HTTPError()
        mock_get.return_value = m
        client = self._make_client()
        with self.assertRaises(Judge0RateLimited):
            client.get_languages()

    @patch('requests.Session.get')
    def test_503_raises_unavailable(self, mock_get):
        m = MagicMock()
        m.status_code = 503
        mock_get.return_value = m
        client = self._make_client()
        with self.assertRaises(Judge0Unavailable):
            client.get_result('tok')

    @patch('requests.Session.get')
    def test_connection_error_raises_unavailable(self, mock_get):
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError('refused')
        client = self._make_client()
        with self.assertRaises(Judge0Unavailable):
            client.get_languages()

    @patch('requests.Session.post')
    def test_timeout_on_submit_raises_unavailable(self, mock_post):
        import requests as req_lib
        mock_post.side_effect = req_lib.Timeout()
        client = self._make_client()
        with self.assertRaises(Judge0Unavailable):
            client.submit('print("x")', '', 71)
