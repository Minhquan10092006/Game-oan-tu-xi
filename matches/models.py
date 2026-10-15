"""
matches/models.py
-----------------
Models quản lý trận đấu giữa AI và AI, hoặc AI và người chơi.
"""
import json
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Match(models.Model):
    """Một trận đấu."""

    STATUS_CHOICES = [
        ('waiting', 'Đang chờ'),
        ('playing', 'Đang chơi'),
        ('finished', 'Kết thúc'),
        ('error', 'Lỗi'),
    ]

    # Người tham gia (player1 luôn là người tạo match)
    player1 = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='matches_as_p1',
    )
    player2 = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='matches_as_p2',
    )
    player1_name = models.CharField(max_length=64, default='Player 1')
    player2_name = models.CharField(max_length=64, default='Player 2')

    # AI submission tham gia (None = human player)
    ai1 = models.ForeignKey(
        'submissions.Submission', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='matches_as_ai1',
    )
    ai2 = models.ForeignKey(
        'submissions.Submission', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='matches_as_ai2',
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='waiting')

    # Trạng thái bàn cờ được serialize thành JSON
    board_state = models.JSONField(default=dict)

    current_player = models.IntegerField(default=1)
    turn_number = models.IntegerField(default=1)
    winner = models.IntegerField(null=True, blank=True)
    win_reason = models.TextField(blank=True)

    max_turns = models.IntegerField(default=200)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Trận đấu'
        verbose_name_plural = 'Trận đấu'

    def __str__(self):
        return f'Match #{self.pk} [{self.status}]'


class MatchMove(models.Model):
    """Một nước đi trong trận đấu."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='moves')
    player = models.IntegerField()
    turn_number = models.IntegerField()

    from_row = models.IntegerField()
    from_col = models.IntegerField()
    to_row = models.IntegerField()
    to_col = models.IntegerField()

    piece_type = models.CharField(max_length=16)
    is_capture = models.BooleanField(default=False)
    captured_type = models.CharField(max_length=16, blank=True)

    # Output thô của AI (để debug)
    ai_raw_output = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['turn_number', 'player']
        verbose_name = 'Nước đi'
        verbose_name_plural = 'Nước đi'

    def __str__(self):
        return (
            f'Move #{self.pk}: P{self.player} '
            f'({self.from_row},{self.from_col})→({self.to_row},{self.to_col})'
        )
