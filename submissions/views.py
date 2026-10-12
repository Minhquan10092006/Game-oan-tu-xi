"""
submissions/views.py
--------------------
REST API endpoints cho bài nộp.

POST /api/submissions/             — tạo bài nộp mới, bắt đầu chấm
GET  /api/submissions/             — liệt kê bài nộp của bản thân
GET  /api/submissions/{id}/        — chi tiết bài nộp
GET  /api/submissions/{id}/result/ — kết quả chấm chi tiết
"""
import logging
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Submission, JudgeResult
from .serializers import (
    SubmissionCreateSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
)
from judge.grader import Grader
from judge.client import Judge0Error, Judge0Unavailable

logger = logging.getLogger(__name__)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """Chỉ owner mới được sửa. Không cho phép đọc bài của người khác."""

    def has_object_permission(self, request, view, obj):
        return obj.submitter == request.user


class SubmissionListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/submissions/  → danh sách bài nộp của user hiện tại
    POST /api/submissions/  → tạo bài nộp mới
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return SubmissionCreateSerializer
        return SubmissionListSerializer

    def get_queryset(self):
        return (
            Submission.objects
            .filter(submitter=self.request.user)
            .order_by('-submitted_at')
        )

    def perform_create(self, serializer):
        submission = serializer.save()
        # Bắt đầu chấm bài bất đồng bộ (chạy trong cùng thread vì chưa có Celery)
        # Trong production nên dùng Celery task
        _grade_submission(submission)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Trả chi tiết sau khi tạo
        instance = serializer.instance
        detail = SubmissionDetailSerializer(instance, context={'request': request})
        return Response(detail.data, status=status.HTTP_201_CREATED)


class SubmissionDetailView(generics.RetrieveAPIView):
    """
    GET /api/submissions/{id}/ → chi tiết bài nộp
    Chỉ owner được xem.
    """
    serializer_class = SubmissionDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return Submission.objects.filter(submitter=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def submission_result_view(request, pk: int):
    """
    GET /api/submissions/{id}/result/ → kết quả chấm chi tiết
    Chỉ owner được xem.
    """
    try:
        sub = Submission.objects.get(pk=pk, submitter=request.user)
    except Submission.DoesNotExist:
        return Response(
            {'error': True, 'message': 'Bài nộp không tồn tại hoặc không có quyền truy cập.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    detailed = JudgeResult.objects.filter(submission=sub)
    result_data = {
        'submission_id': sub.pk,
        'status': sub.status,
        'score': sub.score,
        'error_message': sub.error_message,
        'judged_at': sub.judged_at,
        'groups': [
            {
                'group': r.group,
                'passed': r.passed,
                'score': r.score,
                'max_score': r.max_score,
                'message': r.message,
                'details': r.details,
            }
            for r in detailed
        ],
        'summary': sub.judge_result,
    }
    return Response(result_data)


# ------------------------------------------------------------------ #
# Internal: chấm bài                                                   #
# ------------------------------------------------------------------ #

def _grade_submission(submission: Submission):
    """
    Gọi Grader và lưu kết quả vào DB.
    Chạy synchronous — trong production thay bằng Celery task.
    """
    submission.status = 'running'
    submission.save(update_fields=['status'])

    try:
        grader = Grader()
        report = grader.grade(submission.pk, submission.source_code)
    except Exception as e:
        logger.exception('Grading failed for submission %s', submission.pk)
        submission.status = 'error'
        submission.error_message = f'Lỗi hệ thống chấm bài: {type(e).__name__}'
        submission.judged_at = timezone.now()
        submission.save(update_fields=['status', 'error_message', 'judged_at'])
        return

    # Lưu kết quả từng nhóm
    JudgeResult.objects.filter(submission=submission).delete()
    for g in report.groups:
        JudgeResult.objects.create(
            submission=submission,
            group=g.group,
            passed=g.passed,
            score=g.score,
            max_score=g.max_score,
            message=g.message,
            details=g.details,
        )

    # Cập nhật submission
    submission.status = 'completed' if not report.error else 'error'
    submission.score = report.total_score
    submission.judge_result = report.to_dict()
    submission.error_message = report.error
    submission.judged_at = timezone.now()
    submission.save(update_fields=[
        'status', 'score', 'judge_result', 'error_message', 'judged_at',
    ])
