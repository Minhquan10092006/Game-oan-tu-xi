"""
submissions/views.py
--------------------
REST API cho bài nộp code AI.

Đã bỏ: logic gọi Judge0, chấm điểm, JudgeResult.
Giữ lại: nộp code, xem danh sách, xem chi tiết.
Thêm mới (admin): approve, reject, delete, list-all.
"""
import logging
import hashlib
import json
import uuid
from django.contrib.auth import get_user_model
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Submission, SubmissionReceipt
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
        from web.tournament_ops import can_operate
        return bool(
            request.user and request.user.is_authenticated
            and can_operate(request.user)
        )


# ── User API ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def submission_session(request):
    from django.conf import settings
    response = Response({'user_id': request.user.pk, 'username': request.user.username,
                         'csrf_token': get_token(request),
                         'max_code_size': settings.SUBMISSION_MAX_CODE_SIZE})
    response['Cache-Control'] = 'no-store'
    return response


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
        from web.tournament_ops import can_operate
        if can_operate(request.user):
            return Response({'error': 'Tài khoản admin dùng để quản lý và chấm bài, không nộp bot dự thi.'}, status=403)
        if request.session.get('is_guest'):
            return Response({'error': 'Hãy tạo tài khoản chính thức để nộp bài.'}, status=403)
        payload = request.data.copy()
        client_account_id = payload.pop('client_account_id', None)
        if client_account_id is not None and str(client_account_id) != str(request.user.pk):
            return Response({'error': 'Tài khoản đã thay đổi. Hãy đăng nhập đúng tài khoản của bài chờ.'}, status=409)
        client_id = payload.pop('client_submission_id', None)
        if client_id is not None:
            try:
                client_id = uuid.UUID(str(client_id))
            except (ValueError, TypeError, AttributeError):
                return Response({'error': 'Mã lần nộp không hợp lệ.'}, status=400)
        payload_hash = hashlib.sha256(json.dumps(dict(payload), sort_keys=True, ensure_ascii=False,
                                                 separators=(',', ':')).encode()).hexdigest()
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if client_id:
                receipt = SubmissionReceipt.objects.select_related('submission').filter(
                    submitter=request.user, client_id=client_id).first()
                if receipt:
                    if receipt.payload_hash != payload_hash:
                        return Response({'error': 'Mã lần nộp đã được dùng cho nội dung khác.'}, status=409)
                    return Response(SubmissionDetailSerializer(receipt.submission).data, status=200)
            serializer = self.get_serializer(data=payload, context={'request': request})
            serializer.is_valid(raise_exception=True)
            submission = serializer.save()
            if client_id:
                SubmissionReceipt.objects.create(submitter=request.user, client_id=client_id,
                    payload_hash=payload_hash, submission=submission)
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
    from web.models import OfficialBot
    if OfficialBot.objects.filter(submission=sub).exists():
        return Response({'error': 'Bài đang là phiên bản chính thức của giải; phải giữ để đối chiếu.'}, status=409)
    if sub.used_in_battle:
        return Response({'error': 'Bài đã thi đấu phải được giữ để đối chiếu; không thể xóa.'}, status=409)
    if SubmissionReceipt.objects.filter(submission=sub).exists():
        return Response({'error': 'Bài có biên nhận chống nộp trùng; cần giữ để đối chiếu.'}, status=409)
    sub.delete()
    logger.info('Admin %s deleted submission %s', request.user, sub_info)
    return Response({'ok': True, 'deleted': sub_info})
