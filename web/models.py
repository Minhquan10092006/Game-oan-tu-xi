from django.db import models
from django.db.models import Q
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
    ENTRY_MODE_CHOICES = [('individual', 'Cá nhân'), ('team', 'Đội'), ('both', 'Cá nhân và đội')]
    name = models.CharField(max_length=120, verbose_name='Tên mùa giải')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    start_date = models.DateField(verbose_name='Ngày bắt đầu')
    end_date = models.DateField(null=True, blank=True, verbose_name='Ngày kết thúc')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    entry_mode = models.CharField(max_length=12, choices=ENTRY_MODE_CHOICES, default='both')
    max_team_size = models.PositiveSmallIntegerField(default=4)
    registration_deadline = models.DateTimeField(null=True, blank=True)
    draw_seed = models.CharField(max_length=32, blank=True)
    drawn_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_seasons')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Mùa giải'
        verbose_name_plural = 'Mùa giải'

    def __str__(self):
        return f'{"🟢" if self.is_active else "🔴"} {self.name}'


class Team(models.Model):
    """A season-scoped team. The invitation secret is stored only as a hash."""
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=80)
    captain = models.ForeignKey(User, on_delete=models.PROTECT, related_name='captained_teams')
    join_code_hash = models.CharField(max_length=64, unique=True, editable=False)
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['season', 'name'], name='unique_team_name_per_season')]
        ordering = ['name']

    def __str__(self):
        return f'{self.season.name} / {self.name}'


class TeamMembership(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['team', 'user'], name='unique_member_per_team')]


class CompetitionEntry(models.Model):
    """The immutable competitor identity used by a season: exactly one user or team."""
    STATUS_CHOICES = [('registered', 'Đã đăng ký'), ('locked', 'Đã khóa'), ('withdrawn', 'Rút')]
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='entries')
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='individual_entries')
    team = models.OneToOneField(Team, null=True, blank=True, on_delete=models.CASCADE, related_name='entry')
    display_name = models.CharField(max_length=120)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='registered')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['season', 'user'], condition=Q(user__isnull=False), name='one_individual_entry_per_season'),
            models.CheckConstraint(condition=(Q(user__isnull=False, team__isnull=True) | Q(user__isnull=True, team__isnull=False)), name='entry_has_one_competitor'),
        ]


class TournamentRound(models.Model):
    STAGE_CHOICES = [
        ('group', 'Vòng bảng'), ('round_of_4096', 'Vòng 4096'), ('round_of_2048', 'Vòng 2048'),
        ('round_of_1024', 'Vòng 1024'), ('round_of_512', 'Vòng 512'),
        ('round_of_256', 'Vòng 256'), ('round_of_128', 'Vòng 128'),
        ('round_of_64', 'Vòng 64'), ('round_of_32', 'Vòng 32'), ('round_of_16', 'Vòng 16'),
        ('quarterfinal', 'Tứ kết'), ('semifinal', 'Bán kết'), ('third_place', 'Tranh hạng ba'), ('final', 'Chung kết'),
    ]
    STATUS_CHOICES = [('planned', 'Chưa mở'), ('active', 'Đang diễn ra'), ('completed', 'Hoàn tất')]
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='rounds')
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    format_note = models.CharField(max_length=160, blank=True)
    advance_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='planned')

    class Meta:
        ordering = ['order']
        constraints = [models.UniqueConstraint(fields=['season', 'order'], name='one_round_order_per_season')]


class TournamentGroup(models.Model):
    tournament_round = models.ForeignKey(TournamentRound, on_delete=models.CASCADE, related_name='groups')
    code = models.CharField(max_length=16)
    draw_order = models.PositiveSmallIntegerField(default=0)
    entries = models.ManyToManyField(CompetitionEntry, related_name='groups', blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tournament_round', 'code'], name='unique_group_code_per_round')]


class TournamentFixture(models.Model):
    RESULT_CHOICES = [
        ('scheduled', 'Chưa đấu'), ('entry1_win', 'Đơn vị 1 thắng'),
        ('entry2_win', 'Đơn vị 2 thắng'), ('draw', 'Hòa'), ('bye', 'Miễn vòng'),
    ]
    SLOT_CHOICES = [('entry1', 'Đơn vị 1'), ('entry2', 'Đơn vị 2')]

    tournament_round = models.ForeignKey(TournamentRound, on_delete=models.CASCADE, related_name='fixtures')
    group = models.ForeignKey(TournamentGroup, null=True, blank=True, on_delete=models.CASCADE, related_name='fixtures')
    match_number = models.PositiveSmallIntegerField()
    leg = models.PositiveSmallIntegerField(default=1)
    entry1 = models.ForeignKey(CompetitionEntry, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='fixtures_as_entry1')
    entry2 = models.ForeignKey(CompetitionEntry, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='fixtures_as_entry2')
    source_group1 = models.ForeignKey(TournamentGroup, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='source_fixtures_entry1')
    source_rank1 = models.PositiveSmallIntegerField(null=True, blank=True)
    source_group2 = models.ForeignKey(TournamentGroup, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='source_fixtures_entry2')
    source_rank2 = models.PositiveSmallIntegerField(null=True, blank=True)
    result = models.CharField(max_length=12, choices=RESULT_CHOICES, default='scheduled')
    winner = models.ForeignKey(CompetitionEntry, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='fixtures_won')
    winner_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='incoming_winners')
    winner_to_slot = models.CharField(max_length=6, choices=SLOT_CHOICES, blank=True)
    loser_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='incoming_losers')
    loser_to_slot = models.CharField(max_length=6, choices=SLOT_CHOICES, blank=True)

    class Meta:
        ordering = ['tournament_round__order', 'match_number']
        constraints = [
            models.UniqueConstraint(fields=['tournament_round', 'match_number'], name='unique_match_number_per_round'),
        ]


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
