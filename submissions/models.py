"""
submissions/models.py
---------------------
Models quản lý bài nộp AI của người dùng.
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class Submission(models.Model):
    """Một bài nộp code AI."""

    STATUS_CHOICES = [
        ('pending', 'Chờ chấm'),
        ('queued', 'Đang xếp hàng'),
        ('running', 'Đang chạy'),
        ('completed', 'Hoàn thành'),
        ('failed', 'Thất bại'),
        ('error', 'Lỗi hệ thống'),
    ]

    submitter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    ai_name = models.CharField(
        max_length=128,
        help_text='Tên AI do người dùng đặt',
    )
    source_code = models.TextField(
        help_text='Mã nguồn Python',
    )
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default='pending',
    )
    # Judge0 token để truy vấn kết quả
    judge0_token = models.CharField(max_length=256, blank=True)

    # Điểm chấm tổng (0-100)
    score = models.FloatField(null=True, blank=True)

    # Kết quả chi tiết theo nhóm test (JSON)
    judge_result = models.JSONField(null=True, blank=True)

    # Thông báo lỗi (nếu có)
    error_message = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    judged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Bài nộp'
        verbose_name_plural = 'Bài nộp'
        # Mỗi user có version tăng dần
        unique_together = [('submitter', 'ai_name', 'version')]

    def __str__(self):
        return f'{self.submitter.username} / {self.ai_name} v{self.version}'

    def save(self, *args, **kwargs):
        """Kiểm tra kích thước code trước khi lưu."""
        max_size = getattr(settings, 'SUBMISSION_MAX_CODE_SIZE', 65536)
        if len(self.source_code.encode('utf-8')) > max_size:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                f'Mã nguồn vượt giới hạn {max_size} bytes.'
            )
        super().save(*args, **kwargs)


class JudgeResult(models.Model):
    """Chi tiết kết quả chấm từng nhóm test."""

    GROUP_CHOICES = [
        ('execution', 'Thực thi'),
        ('protocol', 'Giao thức'),
        ('legal_move', 'Nước đi hợp lệ'),
        ('runtime_limit', 'Giới hạn thời gian'),
        ('robustness', 'Độ bền'),
        ('simulation', 'Simulation trận đấu'),
    ]

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='detailed_results',
    )
    group = models.CharField(max_length=32, choices=GROUP_CHOICES)
    passed = models.BooleanField(default=False)
    score = models.FloatField(default=0.0)
    max_score = models.FloatField(default=10.0)
    message = models.TextField(blank=True)
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['group']
        verbose_name = 'Kết quả chấm'
        verbose_name_plural = 'Kết quả chấm'

    def __str__(self):
        status = '✓' if self.passed else '✗'
        return f'{status} {self.submission} — {self.group}'
