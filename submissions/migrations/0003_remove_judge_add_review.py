"""
Migration 0003: Bỏ AI Judge, thêm review workflow cho Submission.

Thay đổi:
- Xóa: judge0_token, score, judge_result, error_message, judged_at, elo, ai_wins, ai_losses
- Xóa model: JudgeResult
- Thêm: review_status, approved_by, approved_at, reject_reason, used_in_battle
- Đổi status choices thành review_status
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_submission_ai_losses_submission_ai_wins_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Xóa model JudgeResult ──────────────────────────────────
        migrations.DeleteModel(name='JudgeResult'),

        # ── Xóa các cột liên quan đến AI Judge ────────────────────
        migrations.RemoveField(model_name='submission', name='judge0_token'),
        migrations.RemoveField(model_name='submission', name='score'),
        migrations.RemoveField(model_name='submission', name='judge_result'),
        migrations.RemoveField(model_name='submission', name='error_message'),
        migrations.RemoveField(model_name='submission', name='judged_at'),
        migrations.RemoveField(model_name='submission', name='elo'),
        migrations.RemoveField(model_name='submission', name='ai_wins'),
        migrations.RemoveField(model_name='submission', name='ai_losses'),

        # ── Đổi tên field status → review_status với choices mới ──
        migrations.RemoveField(model_name='submission', name='status'),
        migrations.AddField(
            model_name='submission',
            name='review_status',
            field=models.CharField(
                choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('rejected', 'Bị từ chối')],
                default='pending', max_length=16, db_index=True,
            ),
        ),

        # ── Thêm review workflow ───────────────────────────────────
        migrations.AddField(
            model_name='submission',
            name='approved_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_submissions',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='submission',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='submission',
            name='reject_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='submission',
            name='used_in_battle',
            field=models.BooleanField(default=False),
        ),
    ]
