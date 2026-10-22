"""
submissions/serializers.py — không còn judge logic.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from .models import Submission


class SubmissionCreateSerializer(serializers.ModelSerializer):
    """Tạo bài nộp mới: chỉ cần ai_name + source_code."""
    source_code = serializers.CharField(trim_whitespace=False)

    class Meta:
        model = Submission
        fields = ['ai_name', 'source_code']

    def validate_source_code(self, value: str) -> str:
        max_size = getattr(settings, 'SUBMISSION_MAX_CODE_SIZE', 65536)
        if len(value.encode('utf-8')) > max_size:
            raise serializers.ValidationError(f'Mã nguồn vượt giới hạn {max_size} bytes.')
        if not value.strip():
            raise serializers.ValidationError('Mã nguồn không được rỗng.')
        # Kiểm tra cú pháp Python
        ok, err = Submission.validate_python_syntax(value)
        if not ok:
            raise serializers.ValidationError(f'Cú pháp Python không hợp lệ: {err}')
        return value

    def validate_ai_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError('Tên AI không được rỗng.')
        return value.strip()

    @transaction.atomic
    def create(self, validated_data):
        user = self.context['request'].user
        # Serialize version allocation and quota checks for each account on PostgreSQL.
        get_user_model().objects.select_for_update().get(pk=user.pk)
        today = timezone.localdate()
        if Submission.objects.filter(submitter=user, submitted_at__date=today).count() >= settings.SUBMISSION_RATE_LIMIT_PER_DAY:
            raise serializers.ValidationError('Đã hết số lượt nộp trong ngày.')
        # Tự động tăng version cho cùng tên AI
        last = (
            Submission.objects
            .filter(submitter=user, ai_name=validated_data['ai_name'])
            .order_by('-version').first()
        )
        version = (last.version + 1) if last else 1
        return Submission.objects.create(
            submitter=user, version=version, **validated_data,
        )


class SubmissionListSerializer(serializers.ModelSerializer):
    """Danh sách bài nộp của user — không trả source_code."""

    class Meta:
        model = Submission
        fields = ['id', 'ai_name', 'version', 'review_status', 'reject_reason', 'submitted_at', 'source_sha256']
        read_only_fields = fields


class SubmissionDetailSerializer(serializers.ModelSerializer):
    """Chi tiết bài nộp — bao gồm source_code."""
    submitter_username = serializers.CharField(source='submitter.username', read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'submitter_username', 'ai_name', 'version',
            'review_status', 'reject_reason',
            'source_code', 'source_sha256', 'submitted_at', 'approved_at', 'used_in_battle',
        ]
        read_only_fields = fields


class ApprovedBotSerializer(serializers.ModelSerializer):
    """Danh sách bot đã được duyệt — dùng cho battlecode."""
    label = serializers.SerializerMethodField()
    submitter_username = serializers.CharField(source='submitter.username', read_only=True)

    class Meta:
        model = Submission
        fields = ['id', 'label', 'ai_name', 'version', 'submitter_username', 'submitted_at']

    def get_label(self, obj):
        return f'{obj.ai_name} v{obj.version} (by {obj.submitter.username})'
