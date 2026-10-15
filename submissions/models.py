"""
submissions/models.py
---------------------
Model quản lý code AI do user nộp.

Thay đổi so với phiên bản cũ:
- Bỏ hoàn toàn judge0_token, score, judge_result, error_message, judged_at, ai_wins, ai_losses, elo
- Đổi status thành review_status: pending / approved / rejected
- Thêm: approved_by, approved_at, reject_reason, used_in_battle
- Giữ: submitter, ai_name, source_code, version, submitted_at
"""

import ast
from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class Submission(models.Model):
    """Một bài nộp code AI của user."""

    REVIEW_STATUS = [
        ('pending',  'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Bị từ chối'),
    ]

    # ── Thông tin cơ bản ──────────────────────────────────────────────
    submitter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='submissions',
    )
    ai_name = models.CharField(max_length=128, help_text='Tên AI do người dùng đặt')
    source_code = models.TextField(help_text='Mã nguồn Python')
    version = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(auto_now_add=True)

    # ── Review workflow (admin) ───────────────────────────────────────
    review_status = models.CharField(
        max_length=16, choices=REVIEW_STATUS, default='pending',
        db_index=True,
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_submissions',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.TextField(blank=True, help_text='Lý do từ chối (admin điền)')

    # ── Dùng trong battle ────────────────────────────────────────────
    used_in_battle = models.BooleanField(
        default=False,
        help_text='Code này đã được dùng trong ít nhất một trận battle',
    )

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Bài nộp'
        verbose_name_plural = 'Bài nộp'
        unique_together = [('submitter', 'ai_name', 'version')]

    def __str__(self):
        status_icon = {'pending': '⏳', 'approved': '✅', 'rejected': '❌'}.get(self.review_status, '?')
        return f'{status_icon} {self.submitter.username} / {self.ai_name} v{self.version}'

    def save(self, *args, **kwargs):
        """Kiểm tra kích thước code trước khi lưu."""
        max_size = getattr(settings, 'SUBMISSION_MAX_CODE_SIZE', 65536)
        if len(self.source_code.encode('utf-8')) > max_size:
            from django.core.exceptions import ValidationError
            raise ValidationError(f'Mã nguồn vượt giới hạn {max_size} bytes.')
        super().save(*args, **kwargs)

    @staticmethod
    def validate_python_syntax(code: str) -> tuple[bool, str]:
        """
        Kiểm tra cú pháp Python cơ bản bằng ast.parse.
        Trả về (ok: bool, error_message: str).
        """
        try:
            ast.parse(code)
            return True, ''
        except SyntaxError as e:
            return False, f'Lỗi cú pháp dòng {e.lineno}: {e.msg}'
        except Exception as e:
            return False, str(e)

    @property
    def is_approved(self):
        return self.review_status == 'approved'

    @property
    def short_code(self):
        """Trả về 5 dòng đầu để preview."""
        lines = self.source_code.splitlines()
        preview = '\n'.join(lines[:5])
        return preview + ('\n...' if len(lines) > 5 else '')
