"""
submissions/tests.py
--------------------
Test API và model bài nộp — phiên bản mới (không có Judge0/JudgeResult).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from .models import Submission

User = get_user_model()

VALID_AI_CODE = '''\
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


class TestSubmissionModel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass123')

    def test_create_submission(self):
        """Tạo submission thành công với trạng thái mặc định pending."""
        sub = Submission.objects.create(
            submitter=self.user,
            ai_name='TestAI',
            source_code='print("hello")',
            version=1,
        )
        self.assertEqual(sub.review_status, 'pending')
        self.assertEqual(sub.version, 1)
        self.assertFalse(sub.used_in_battle)

    def test_code_size_limit(self):
        """Code vượt giới hạn 64 KB bị từ chối."""
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

    def test_validate_python_syntax_valid(self):
        """Cú pháp Python hợp lệ → (True, '')."""
        ok, err = Submission.validate_python_syntax('x = 1 + 2')
        self.assertTrue(ok)
        self.assertEqual(err, '')

    def test_validate_python_syntax_invalid(self):
        """Cú pháp Python sai → (False, message có chứa lỗi)."""
        ok, err = Submission.validate_python_syntax('def broken(((')
        self.assertFalse(ok)
        self.assertIn('pháp', err.lower())  # "Lỗi cú pháp..."

    def test_is_approved_property(self):
        sub = Submission.objects.create(
            submitter=self.user, ai_name='AI', source_code='x=1', version=1,
        )
        self.assertFalse(sub.is_approved)
        sub.review_status = 'approved'
        sub.save()
        sub.refresh_from_db()
        self.assertTrue(sub.is_approved)

    def test_version_auto_increment_via_serializer(self):
        """Serializer tự tăng version khi cùng tên AI."""
        from .serializers import SubmissionCreateSerializer
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.post('/')
        request.user = self.user

        data = {'ai_name': 'MyAI', 'source_code': VALID_AI_CODE}

        s1 = SubmissionCreateSerializer(data=data, context={'request': request})
        self.assertTrue(s1.is_valid(), s1.errors)
        sub1 = s1.save()
        self.assertEqual(sub1.version, 1)

        s2 = SubmissionCreateSerializer(data=data, context={'request': request})
        self.assertTrue(s2.is_valid(), s2.errors)
        sub2 = s2.save()
        self.assertEqual(sub2.version, 2)


class TestSubmissionAPI(TestCase):
    def setUp(self):
        self.user       = User.objects.create_user(username='apiuser',  password='pass123')
        self.other_user = User.objects.create_user(username='other',    password='pass123')
        self.admin_user = User.objects.create_user(username='adminusr', password='pass123',
                                                   is_staff=True)
        self.client = APIClient()

    # ── User endpoints ──────────────────────────────────────────────

    def test_unauthenticated_cannot_create(self):
        resp = self.client.post('/api/submissions/', {
            'ai_name': 'AI', 'source_code': 'print(1)',
        })
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_submission_success(self):
        """POST /api/submissions/ — lưu code, không chấm điểm."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/submissions/', {
            'ai_name': 'MyAI',
            'source_code': VALID_AI_CODE,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', resp.data)
        self.assertEqual(resp.data['review_status'], 'pending')
        # Không có field điểm / score
        self.assertNotIn('score', resp.data)
        self.assertNotIn('judge_result', resp.data)

    def test_empty_code_rejected(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/submissions/', {
            'ai_name': 'AI', 'source_code': '   ',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_syntax_error_rejected(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post('/api/submissions/', {
            'ai_name': 'BrokenAI',
            'source_code': 'def broken((((',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_see_others_submissions(self):
        Submission.objects.create(
            submitter=self.other_user, ai_name='OtherAI',
            source_code='print(1)', version=1,
        )
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/submissions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 0)   # chỉ thấy bài của mình

    def test_user_cannot_access_others_submission_by_id(self):
        sub = Submission.objects.create(
            submitter=self.other_user, ai_name='OtherAI',
            source_code='print(1)', version=1,
        )
        self.client.force_authenticate(user=self.user)
        resp = self.client.get(f'/api/submissions/{sub.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_approved_bots_endpoint(self):
        """GET /api/submissions/approved/ trả danh sách đã duyệt."""
        Submission.objects.create(
            submitter=self.user, ai_name='ApprovedAI',
            source_code='print(1)', version=1,
            review_status='approved',
        )
        Submission.objects.create(
            submitter=self.user, ai_name='PendingAI',
            source_code='print(2)', version=1,
            review_status='pending',
        )
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/submissions/approved/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['ai_name'], 'ApprovedAI')

    # ── Admin endpoints ─────────────────────────────────────────────

    def test_non_admin_cannot_approve(self):
        sub = Submission.objects.create(
            submitter=self.other_user, ai_name='TestAI',
            source_code='print(1)', version=1,
        )
        self.client.force_authenticate(user=self.user)  # bình thường, không phải admin
        resp = self.client.post(f'/api/submissions/admin/{sub.pk}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_approve(self):
        sub = Submission.objects.create(
            submitter=self.other_user, ai_name='TestAI',
            source_code='print(1)', version=1,
        )
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.post(f'/api/submissions/admin/{sub.pk}/approve/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.review_status, 'approved')
        self.assertEqual(sub.approved_by, self.admin_user)

    def test_admin_can_reject_with_reason(self):
        sub = Submission.objects.create(
            submitter=self.other_user, ai_name='BadAI',
            source_code='print(1)', version=1,
        )
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.post(
            f'/api/submissions/admin/{sub.pk}/reject/',
            {'reason': 'Vi phạm quy định'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sub.refresh_from_db()
        self.assertEqual(sub.review_status, 'rejected')
        self.assertEqual(sub.reject_reason, 'Vi phạm quy định')

    def test_admin_can_delete(self):
        sub = Submission.objects.create(
            submitter=self.other_user, ai_name='ViolatingAI',
            source_code='print(1)', version=1,
        )
        pk = sub.pk
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.delete(f'/api/submissions/admin/{pk}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Submission.objects.filter(pk=pk).exists())

    def test_admin_list_with_filter(self):
        Submission.objects.create(
            submitter=self.user, ai_name='PendingAI',
            source_code='print(1)', version=1, review_status='pending',
        )
        Submission.objects.create(
            submitter=self.user, ai_name='ApprovedAI',
            source_code='print(2)', version=1, review_status='approved',
        )
        self.client.force_authenticate(user=self.admin_user)
        # Filter chỉ lấy pending
        resp = self.client.get('/api/submissions/admin/list/?status=pending')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['ai_name'], 'PendingAI')
