"""
submissions/serializers.py — không còn judge logic.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from urllib.parse import urlparse
import re
from .models import Submission


GIT_REFERENCE_HOSTS = {'github.com', 'gitlab.com'}


class SubmissionCreateSerializer(serializers.ModelSerializer):
    """Tạo bài nộp mới: chỉ cần ai_name + source_code."""
    source_code = serializers.CharField(trim_whitespace=False)

    class Meta:
        model = Submission
        fields = ['ai_name', 'source_code', 'competition_entry', 'submission_method', 'git_url', 'git_commit']

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

    def validate(self, attrs):
        method = attrs.get('submission_method', 'direct')
        url, commit = attrs.get('git_url', '').strip(), attrs.get('git_commit', '').strip().lower()
        if method == 'git':
            parsed = urlparse(url)
            path_parts = [part for part in parsed.path.split('/') if part]
            if (parsed.scheme != 'https' or parsed.hostname not in GIT_REFERENCE_HOSTS or parsed.username or
                    parsed.password or parsed.port or parsed.query or parsed.fragment or len(path_parts) < 2):
                raise serializers.ValidationError({'git_url': 'Chỉ nhận URL HTTPS GitHub/GitLab không có token, query hoặc fragment.'})
            if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
                raise serializers.ValidationError({'git_commit': 'Cần mã commit đầy đủ 40 hoặc 64 ký tự hexadecimal.'})
        elif url or commit:
            raise serializers.ValidationError('Chọn phương thức Git khi khai báo URL hoặc commit Git.')
        attrs['git_url'], attrs['git_commit'] = url, commit
        entry = attrs.get('competition_entry')
        if entry:
            request = self.context['request']
            if entry.status != 'registered':
                raise serializers.ValidationError({'competition_entry': 'Mục dự thi đã bị khóa hoặc rút.'})
            if entry.user_id != request.user.id:
                if not entry.team_id or entry.team.captain_id != request.user.id:
                    raise serializers.ValidationError({'competition_entry': 'Chỉ đội trưởng mới được nộp bài chính thức cho đội.'})
        return attrs

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
        fields = ['id', 'ai_name', 'version', 'review_status', 'reject_reason', 'submitted_at', 'source_sha256',
                  'competition_entry', 'submission_method', 'git_url', 'git_commit']
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
            'competition_entry', 'submission_method', 'git_url', 'git_commit',
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
