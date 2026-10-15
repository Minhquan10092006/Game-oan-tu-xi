from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
import json

User = get_user_model()

ELO_DEFAULT = 1200
ELO_K_FACTOR = 32  # hệ số điều chỉnh mỗi trận


class UserProfile(models.Model):
    """Thông tin ELO và thống kê của mỗi user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    elo = models.IntegerField(default=ELO_DEFAULT)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    draws = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-elo']
        verbose_name = 'Hồ sơ người dùng'
        verbose_name_plural = 'Hồ sơ người dùng'

    def __str__(self):
        return f'{self.user.username} (ELO {self.elo})'

    @property
    def total_games(self):
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self):
        if self.total_games == 0:
            return 0.0
        return round(self.wins / self.total_games * 100, 1)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Tự động tạo UserProfile khi tạo User mới."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


def calculate_elo(winner_elo: int, loser_elo: int, k: int = ELO_K_FACTOR):
    """
    Tính ELO mới sau trận đấu.
    Trả về (new_winner_elo, new_loser_elo).

    Công thức:
        expected_winner = 1 / (1 + 10^((loser - winner) / 400))
        delta = K * (1 - expected_winner)
    """
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    delta = round(k * (1 - expected_winner))
    return winner_elo + delta, loser_elo - delta


def update_elo_after_match(winner_user, loser_user):
    """
    Cập nhật ELO cho hai người chơi sau trận đấu.
    Trả về (winner_profile, loser_profile).
    """
    w_profile, _ = UserProfile.objects.get_or_create(user=winner_user)
    l_profile, _ = UserProfile.objects.get_or_create(user=loser_user)

    new_w, new_l = calculate_elo(w_profile.elo, l_profile.elo)

    w_profile.elo = new_w
    w_profile.wins += 1
    w_profile.save(update_fields=['elo', 'wins', 'updated_at'])

    l_profile.elo = new_l
    l_profile.losses += 1
    l_profile.save(update_fields=['elo', 'losses', 'updated_at'])

    return w_profile, l_profile


class Season(models.Model):
    name = models.CharField(max_length=120, verbose_name='Tên mùa giải')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    start_date = models.DateField(verbose_name='Ngày bắt đầu')
    end_date = models.DateField(null=True, blank=True, verbose_name='Ngày kết thúc')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_seasons')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Mùa giải'
        verbose_name_plural = 'Mùa giải'

    def __str__(self):
        return f'{"🟢" if self.is_active else "🔴"} {self.name}'


class MatchHistory(models.Model):
    RESULT_CHOICES = [('p1_win','P1 thắng'),('p2_win','P2 thắng'),('draw','Hòa'),('error','Lỗi')]

    match_id = models.CharField(max_length=64, unique=True)
    player = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='match_histories')
    season = models.ForeignKey(Season, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='matches')
    board_preset = models.CharField(max_length=60, default='classic_9x9')
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    winner = models.CharField(max_length=10, blank=True)
    total_plies = models.IntegerField(default=0)
    reason_code = models.CharField(max_length=60, blank=True)
    reason_message = models.TextField(blank=True)
    replay_data = models.TextField(blank=True)
    player1_filename = models.CharField(max_length=255, blank=True)
    player2_filename = models.CharField(max_length=255, blank=True)
    played_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-played_at']
        verbose_name = 'Lịch sử trận đấu'
        verbose_name_plural = 'Lịch sử trận đấu'

    def __str__(self):
        who = self.player.username if self.player else 'Guest'
        return f'{who} — {self.board_preset} — {self.result} ({self.played_at:%Y-%m-%d %H:%M})'

    def get_replay(self):
        try:
            return json.loads(self.replay_data) if self.replay_data else None
        except Exception:
            return None
