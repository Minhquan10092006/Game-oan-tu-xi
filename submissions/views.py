"""
submissions/views.py
--------------------
REST API cho bài nộp code AI.

Đã bỏ: logic gọi Judge0, chấm điểm, JudgeResult.
Giữ lại: nộp code, xem danh sách, xem chi tiết.
Thêm mới (admin): approve, reject, delete, list-all.
"""
import logging
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Submission
from .serializers import (
    SubmissionCreateSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
    ApprovedBotSerializer,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────

class IsAdminUser(permissions.BasePermission):
    """Chỉ cho phép staff / superuser."""
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )


# ── User API ──────────────────────────────────────────────────────────

class SubmissionListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/submissions/  → danh sách bài nộp của user hiện tại
    POST /api/submissions/  → tạo bài nộp mới (chỉ lưu, không chấm)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return SubmissionCreateSerializer if self.request.method == 'POST' else SubmissionListSerializer

    def get_queryset(self):
        return Submission.objects.filter(submitter=self.request.user).order_by('-submitted_at')

    def create(self, request, *args, **kwargs):
        if request.session.get('is_guest'):
            return Response({'error': 'Hãy tạo tài khoản chính thức để nộp bài.'}, status=403)
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        detail = SubmissionDetailSerializer(submission, context={'request': request})
        logger.info('New submission: user=%s ai=%s v%s', request.user, submission.ai_name, submission.version)
        return Response(detail.data, status=status.HTTP_201_CREATED)


class SubmissionDetailView(generics.RetrieveAPIView):
    """GET /api/submissions/{id}/ → chi tiết bài nộp (chỉ owner)."""
    serializer_class = SubmissionDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Submission.objects.filter(submitter=self.request.user)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def approved_bots_list(request):
    """
    GET /api/submissions/approved/
    Trả danh sách tất cả code đã được admin duyệt.
    Dùng để populate dropdown trong battlecode.
    """
    bots = Submission.objects.filter(review_status='approved').select_related('submitter')
    serializer = ApprovedBotSerializer(bots, many=True)
    return Response(serializer.data)


# ── Admin API ─────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_submission_list(request):
    """
    GET /api/submissions/admin/list/
    Danh sách tất cả bài nộp (admin only).
    Hỗ trợ filter: ?status=pending|approved|rejected
    """
    qs = Submission.objects.select_related('submitter', 'approved_by').order_by('-submitted_at')
    review_status = request.GET.get('status')
    if review_status in ('pending', 'approved', 'rejected'):
        qs = qs.filter(review_status=review_status)
    serializer = SubmissionDetailSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_approve_submission(request, pk):
    """
    POST /api/submissions/admin/{id}/approve/
    Admin duyệt một bài nộp — chuyển review_status → 'approved'.
    """
    try:
        sub = Submission.objects.get(pk=pk)
    except Submission.DoesNotExist:
        return Response({'error': 'Không tìm thấy bài nộp.'}, status=status.HTTP_404_NOT_FOUND)

    sub.review_status = 'approved'
    sub.approved_by = request.user
    sub.approved_at = timezone.now()
    sub.reject_reason = ''          # xoá lý do từ chối cũ nếu có
    sub.save(update_fields=['review_status', 'approved_by', 'approved_at', 'reject_reason'])

    logger.info('Admin %s approved submission #%s (%s by %s)',
                request.user, sub.pk, sub.ai_name, sub.submitter)
    return Response({
        'ok': True,
        'id': sub.pk,
        'review_status': sub.review_status,
        'approved_by': request.user.username,
        'approved_at': sub.approved_at.isoformat(),
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_reject_submission(request, pk):
    """
    POST /api/submissions/admin/{id}/reject/
    Body (JSON, optional): { "reason": "..." }
    Admin từ chối bài nộp — chuyển review_status → 'rejected'.
    """
    try:
        sub = Submission.objects.get(pk=pk)
    except Submission.DoesNotExist:
        return Response({'error': 'Không tìm thấy bài nộp.'}, status=status.HTTP_404_NOT_FOUND)

    reason = (request.data.get('reason') or '').strip()
    sub.review_status = 'rejected'
    sub.reject_reason = reason
    sub.approved_by = None
    sub.approved_at = None
    sub.save(update_fields=['review_status', 'reject_reason', 'approved_by', 'approved_at'])

    logger.info('Admin %s rejected submission #%s (%s by %s). Reason: %s',
                request.user, sub.pk, sub.ai_name, sub.submitter, reason or '(none)')
    return Response({
        'ok': True,
        'id': sub.pk,
        'review_status': sub.review_status,
        'reject_reason': sub.reject_reason,
    })


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_delete_submission(request, pk):
    """
    DELETE /api/submissions/admin/{id}/delete/
    Admin xoá hẳn bài nộp vi phạm.
    """
    try:
        sub = Submission.objects.get(pk=pk)
    except Submission.DoesNotExist:
        return Response({'error': 'Không tìm thấy bài nộp.'}, status=status.HTTP_404_NOT_FOUND)

    sub_info = f'#{sub.pk} {sub.ai_name} by {sub.submitter}'
    if sub.used_in_battle:
        return Response({'error': 'Bài đã thi đấu phải được giữ để đối chiếu; không thể xóa.'}, status=409)
    sub.delete()
    logger.info('Admin %s deleted submission %s', request.user, sub_info)
    return Response({'ok': True, 'deleted': sub_info})
