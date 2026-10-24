"""
submissions/serializers.py — không còn judge logic.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from .models import Submission


GIT_REFERENCE_HOSTS = {'github.com', 'gitlab.com'}


class SubmissionCreateSerializer(serializers.ModelSerializer):
    """Tạo bài nộp mới: chỉ cần ai_name + source_code."""
    source_code = serializers.CharField(trim_whitespace=False)
    practice = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = Submission
        fields = ['ai_name', 'source_code', 'competition_entry', 'submission_method', 'git_url', 'git_commit', 'practice']

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
        # Public workflow only accepts the Python source. Legacy Git columns stay
        # readable for old records but are no longer a decision users need to make.
        attrs['submission_method'], attrs['git_url'], attrs['git_commit'] = 'direct', '', ''
        entry = attrs.get('competition_entry')
        if entry and attrs.get('practice'):
            raise serializers.ValidationError('Bài luyện tập không được gắn với mục dự thi mùa giải.')
        if not entry and not attrs.get('practice'):
            from web.models import CompetitionEntry
            candidates = list(CompetitionEntry.objects.filter(
                user=self.context['request'].user, status='registered', season__is_active=True,
                season__phase__in=['registration', 'submission'],
            ).filter(Q(season__submission_deadline__isnull=True) | Q(season__submission_deadline__gte=timezone.now()))[:2])
            if len(candidates) > 1:
                raise serializers.ValidationError({'competition_entry': 'Bạn có nhiều mùa đang nhận bài. Hãy chọn đúng mùa giải khi nộp.'})
            if candidates:
                entry = attrs['competition_entry'] = candidates[0]
        if entry:
            request = self.context['request']
            if entry.status != 'registered':
                raise serializers.ValidationError({'competition_entry': 'Mục dự thi đã bị khóa hoặc rút.'})
            if entry.user_id != request.user.id:
                if not entry.team_id or entry.team.captain_id != request.user.id:
                    raise serializers.ValidationError({'competition_entry': 'Chỉ tài khoản đại diện được nộp bài cho mục dự thi này.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('practice', None)
        user = self.context['request'].user
        entry = validated_data.get('competition_entry')
        if entry:
            from web.models import Season, CompetitionEntry
            season = Season.objects.select_for_update().get(pk=entry.season_id)
            current = CompetitionEntry.objects.select_for_update().get(pk=entry.pk)
            if (current.status != 'registered' or season.phase not in ('registration', 'submission')
                    or not season.is_active
                    or (season.submission_deadline and timezone.now() > season.submission_deadline)):
                raise serializers.ValidationError('Mùa giải đã khóa hoặc hết hạn nộp bài.')
            from web.models import OfficialBot, JudgingJob
            existing_bot = OfficialBot.objects.filter(entry=current).first()
            if existing_bot and JudgingJob.objects.filter(bot=existing_bot, state='running').exists():
                raise serializers.ValidationError('Bot đang được kiểm tra; hãy chờ xong trước khi nộp bản mới.')
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
        submission = Submission.objects.create(
            submitter=user, version=version, **validated_data,
        )
        if entry:
            from web.models import OfficialBot, JudgingJob
            # A new submission is always the version used for this entry. Old
            # versions remain as history, but never make an admin choose one.
            bot, _ = OfficialBot.objects.update_or_create(entry=entry, defaults={
                'submission': submission, 'source_code': submission.source_code, 'sha256': submission.source_sha256,
            })
            JudgingJob.objects.filter(bot=bot, kind='validation').exclude(state='running').delete()
        return submission


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
