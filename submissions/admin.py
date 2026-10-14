"""
submissions/admin.py
--------------------
Đăng ký model Submission vào Django Admin.
Đã bỏ: JudgeResult, score, judge0_token, judged_at.
"""

from django.contrib import admin
from django.utils import timezone
from .models import Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'submitter', 'ai_name', 'version',
        'review_status', 'approved_by', 'submitted_at',
    ]
    list_filter = ['review_status']
    search_fields = ['submitter__username', 'ai_name']
    readonly_fields = ['submitted_at', 'approved_at', 'used_in_battle']
    raw_id_fields = ['submitter', 'approved_by']

    # Cho phép approve/reject ngay từ list view
    actions = ['action_approve', 'action_reject']

    @admin.action(description='✅ Duyệt (approve) các bài nộp đã chọn')
    def action_approve(self, request, queryset):
        updated = queryset.update(
            review_status='approved',
            approved_by=request.user,
            approved_at=timezone.now(),
            reject_reason='',
        )
        self.message_user(request, f'Đã duyệt {updated} bài nộp.')

    @admin.action(description='❌ Từ chối (reject) các bài nộp đã chọn')
    def action_reject(self, request, queryset):
        updated = queryset.update(review_status='rejected')
        self.message_user(request, f'Đã từ chối {updated} bài nộp.')
