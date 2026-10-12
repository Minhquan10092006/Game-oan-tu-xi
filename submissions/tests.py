"""
submissions/tests.py
--------------------
Test API và model bài nộp.
Dùng mock để không cần gọi Judge0 thật.
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from .models import Submission, JudgeResult
from judge.client import Judge0Result

User = get_user_model()

VALID_AI_CODE = '''
import sys, json

data = json.loads(sys.stdin.read())
moves = data.get('legal_moves', [])
if moves:
    m = moves[0]
    print(json.dumps({"move": {
        "from_row": m["from_row"], "from_col": m["from_col"],
        "to_row": m["to_row"], "to_col": m["to_col"]
    }}))
else:
    print(json.dumps({"move": None}))
'''


def _make_mock_result(
    stdout='{"move": {"from_row": 2, "from_col": 0, "to_row": 3, "to_col": 0}}',
    status_id=3,
    status_desc='Accepted',
    compile_output='',
    stderr='',
):
    return Judge0Result(
        token='mock-token-abc',
        status_id=status_id,
        status_description=status_desc,
        stdout=stdout,
        stderr=stderr,
        compile_output=compile_output,
    )


class TestSubmissionModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass123')

    def test_create_submission(self):
        sub = Submission.objects.create(
            submitter=self.user,
            ai_name='TestAI',
            source_code='print("hello")',
            version=1,
        )
        self.assertEqual(sub.status, 'pending')
        self.assertEqual(sub.version, 1)

    def test_code_size_limit(self):
        from django.core.exceptions import ValidationError
        big_code = 'x' * 70000
        sub = Submission(
            submitter=self.user,
            ai_name='BigAI',
            source_code=big_code,
            version=1,
        )
        with self.assertRaises(ValidationError):
            sub.save()

    def test_version_auto_increment_via_serializer(self):
        from .serializers import SubmissionCreateSerializer
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.post('/')
        request.user = self.user

        data = {'ai_name': 'MyAI', 'source_code': 'print(1)'}
        s = SubmissionCreateSerializer(data=data, context={'request': request})
        self.assertTrue(s.is_valid(), s.errors)
        sub1 = s.save()
        self.assertEqual(sub1.version, 1)

        s2 = SubmissionCreateSerializer(data=data, context={'request': request})
        self.assertTrue(s2.is_valid(), s2.errors)
        sub2 = s2.save()
        self.assertEqual(sub2.version, 2)


class TestSubmissionAPI(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='apiuser', password='pass123')
        self.other_user = User.objects.create_user(username='other', password='pass123')
        self.client = APIClient()

    def test_unauthenticated_cannot_create(self):
        resp = self.client.post('/api/submissions/', {
            'ai_name': 'AI',
            'source_code': 'print(1)',
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch('submissions.views._grade_submission')
    def test_create_submission_success(self, mock_grade):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/submissions/', {
            'ai_name': 'MyAI',
            'source_code': VALID_AI_CODE,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', resp.data)
        mock_grade.assert_called_once()

    @patch('submissions.views._grade_submission')
    def test_empty_code_rejected(self, mock_grade):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/submissions/', {
            'ai_name': 'AI',
            'source_code': '   ',
        })
        self.assertIn(resp.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ])
        mock_grade.assert_not_called()

    @patch('submissions.views._grade_submission')
    def test_user_cannot_see_others_submissions(self, mock_grade):
        # Tạo bài nộp của other_user
        Submission.objects.create(
            submitter=self.other_user,
            ai_name='OtherAI',
            source_code='print(1)',
            version=1,
        )
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/submissions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Chỉ thấy bài của mình (0 bài)
        self.assertEqual(len(resp.data), 0)

    @patch('submissions.views._grade_submission')
    def test_user_cannot_access_others_submission_by_id(self, mock_grade):
        sub = Submission.objects.create(
            submitter=self.other_user,
            ai_name='OtherAI',
            source_code='print(1)',
            version=1,
        )
        self.client.force_authenticate(user=self.user)
        resp = self.client.get(f'/api/submissions/{sub.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class TestGraderIntegration(TestCase):
    """
    Test bộ chấm với mock Judge0 (không gọi API thật).
    """

    def setUp(self):
        self.user = User.objects.create_user(username='graderuser', password='pass')

    @patch('judge.client.Judge0Client.get_languages')
    @patch('judge.client.Judge0Client.submit_and_wait')
    def test_grade_valid_code(self, mock_wait, mock_langs):
        """Code hợp lệ → execution passed."""
        mock_langs.return_value = [{'id': 71, 'name': 'Python (3.8.1)'}]

        # Trả output hợp lệ cho mọi lần gọi
        valid_output = '{"move": {"from_row": 2, "from_col": 0, "to_row": 3, "to_col": 0}}'
        mock_wait.return_value = _make_mock_result(stdout=valid_output)

        from judge.grader import Grader
        grader = Grader()
        report = grader.grade(1, VALID_AI_CODE)

        # Nhóm execution phải pass
        exec_group = next(g for g in report.groups if g.group == 'execution')
        self.assertTrue(exec_group.passed)

    @patch('judge.client.Judge0Client.get_languages')
    @patch('judge.client.Judge0Client.submit_and_wait')
    def test_grade_syntax_error(self, mock_wait, mock_langs):
        """Code lỗi cú pháp → execution failed."""
        mock_langs.return_value = [{'id': 71, 'name': 'Python (3.8.1)'}]
        mock_wait.return_value = _make_mock_result(
            status_id=6,
            status_desc='Compilation Error',
            compile_output='SyntaxError: invalid syntax',
        )

        from judge.grader import Grader
        grader = Grader()
        report = grader.grade(1, 'def broken_python(((')

        exec_group = next(g for g in report.groups if g.group == 'execution')
        self.assertFalse(exec_group.passed)
        self.assertEqual(exec_group.score, 0)

    @patch('judge.client.Judge0Client.get_languages')
    @patch('judge.client.Judge0Client.submit_and_wait')
    def test_grade_invalid_json_output(self, mock_wait, mock_langs):
        """Output không phải JSON → protocol failed."""
        mock_langs.return_value = [{'id': 71, 'name': 'Python (3.8.1)'}]
        # Execution passed nhưng output sai format
        mock_wait.return_value = _make_mock_result(stdout='not valid json here')

        from judge.grader import Grader
        grader = Grader()
        report = grader.grade(1, 'print("not json")')

        proto_group = next((g for g in report.groups if g.group == 'protocol'), None)
        if proto_group:
            self.assertFalse(proto_group.passed)

    @patch('judge.client.Judge0Client.get_languages')
    @patch('judge.client.Judge0Client.submit_and_wait')
    def test_grade_invalid_move(self, mock_wait, mock_langs):
        """Nước đi không hợp lệ → legal_move failed."""
        mock_langs.return_value = [{'id': 71, 'name': 'Python (3.8.1)'}]
        # JSON đúng format nhưng nước đi không hợp lệ
        mock_wait.return_value = _make_mock_result(
            stdout='{"move": {"from_row": 0, "from_col": 0, "to_row": 5, "to_col": 5}}'
        )

        from judge.grader import Grader
        grader = Grader()
        report = grader.grade(1, 'print("fake")')

        legal_group = next((g for g in report.groups if g.group == 'legal_move'), None)
        if legal_group:
            self.assertFalse(legal_group.passed)

    @patch('judge.client.Judge0Client.get_languages')
    @patch('judge.client.Judge0Client.submit_and_wait')
    def test_grade_tle(self, mock_wait, mock_langs):
        """TLE → runtime_limit failed."""
        mock_langs.return_value = [{'id': 71, 'name': 'Python (3.8.1)'}]
        # Execution lần đầu pass, runtime test TLE
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Execution pass
                return _make_mock_result()
            # Runtime test: TLE
            return _make_mock_result(status_id=5, status_desc='Time Limit Exceeded')

        mock_wait.side_effect = side_effect
        from judge.grader import Grader
        grader = Grader()
        report = grader.grade(1, 'while True: pass')

        runtime_group = next((g for g in report.groups if g.group == 'runtime_limit'), None)
        if runtime_group:
            self.assertFalse(runtime_group.passed)

    @patch('judge.client.Judge0Client.get_languages')
    @patch('judge.client.Judge0Client.submit_and_wait')
    def test_judge0_unavailable_handled(self, mock_wait, mock_langs):
        """Judge0 không khả dụng → không crash, trả error."""
        mock_langs.return_value = [{'id': 71, 'name': 'Python (3.8.1)'}]
        from judge.client import Judge0Unavailable
        mock_wait.side_effect = Judge0Unavailable('Connection refused')

        from judge.grader import Grader
        grader = Grader()
        report = grader.grade(1, 'print("test")')

        # Phải xử lý được, không crash
        self.assertIsNotNone(report)
        exec_group = next((g for g in report.groups if g.group == 'execution'), None)
        self.assertIsNotNone(exec_group)
        self.assertFalse(exec_group.passed)
