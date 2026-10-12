from django.contrib import admin
from .models import Submission, JudgeResult


class JudgeResultInline(admin.TabularInline):
    model = JudgeResult
    extra = 0
    readonly_fields = ['group', 'passed', 'score', 'max_score', 'message', 'created_at']


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'submitter', 'ai_name', 'version', 'status', 'score', 'submitted_at']
    list_filter = ['status']
    search_fields = ['submitter__username', 'ai_name']
    readonly_fields = ['submitted_at', 'judged_at', 'judge0_token']
    inlines = [JudgeResultInline]


@admin.register(JudgeResult)
class JudgeResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'submission', 'group', 'passed', 'score', 'max_score']
    list_filter = ['group', 'passed']
