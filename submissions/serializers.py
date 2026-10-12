"""
submissions/serializers.py
"""
from django.conf import settings
from rest_framework import serializers
from .models import Submission, JudgeResult


class JudgeResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = JudgeResult
        fields = ['group', 'passed', 'score', 'max_score', 'message', 'details']


class SubmissionCreateSerializer(serializers.ModelSerializer):
    """Dùng để tạo bài nộp mới."""

    class Meta:
        model = Submission
        fields = ['ai_name', 'source_code']

    def validate_source_code(self, value: str) -> str:
        max_size = getattr(settings, 'SUBMISSION_MAX_CODE_SIZE', 65536)
        if len(value.encode('utf-8')) > max_size:
            raise serializers.ValidationError(
                f'Mã nguồn vượt giới hạn {max_size} bytes.'
            )
        if not value.strip():
            raise serializers.ValidationError('Mã nguồn không được rỗng.')
        return value

    def validate_ai_name(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError('Tên AI không được rỗng.')
        return value.strip()

    def create(self, validated_data):
        user = self.context['request'].user
        # Tự động tăng version
        last = (
            Submission.objects
            .filter(submitter=user, ai_name=validated_data['ai_name'])
            .order_by('-version')
            .first()
        )
        version = (last.version + 1) if last else 1
        return Submission.objects.create(
            submitter=user,
            version=version,
            **validated_data,
        )


class SubmissionDetailSerializer(serializers.ModelSerializer):
    """Dùng để trả chi tiết bài nộp."""
    detailed_results = JudgeResultSerializer(many=True, read_only=True)
    submitter_username = serializers.CharField(source='submitter.username', read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'submitter_username', 'ai_name', 'version',
            'status', 'score', 'error_message',
            'submitted_at', 'judged_at',
            'judge_result', 'detailed_results',
        ]
        read_only_fields = fields


class SubmissionListSerializer(serializers.ModelSerializer):
    """Dùng để liệt kê bài nộp (không trả source code)."""
    submitter_username = serializers.CharField(source='submitter.username', read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'submitter_username', 'ai_name', 'version',
            'status', 'score', 'submitted_at',
        ]
        read_only_fields = fields
