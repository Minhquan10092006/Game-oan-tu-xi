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
    student_id = models.CharField(max_length=40, blank=True)
    class_name = models.CharField(max_length=80, blank=True)
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
    PHASES = [(key, label) for key, label in [('registration', 'Đăng ký'), ('submission', 'Nộp bài'), ('locked', 'Khóa bài'), ('running', 'Thi đấu'), ('completed', 'Kết thúc')]]
    phase = models.CharField(max_length=16, choices=PHASES, default='registration')
    max_participants = models.PositiveIntegerField(default=4000)
    submission_deadline = models.DateTimeField(null=True, blank=True)
    appeal_deadline = models.DateTimeField(null=True, blank=True)
    require_verified_email = models.BooleanField(default=False)
    judging_paused = models.BooleanField(default=False)
    judge_image = models.CharField(max_length=80, blank=True)
    judge_engine = models.CharField(max_length=64, blank=True)
    ENTRY_MODE_CHOICES = [('individual', 'Cá nhân'), ('team', 'Đội'), ('both', 'Cá nhân và đội')]
    name = models.CharField(max_length=120, verbose_name='Tên mùa giải')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    problem_statement = models.TextField(blank=True, verbose_name='Đặc tả đề bài')
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

    @property
    def submissions_open(self):
        """Deadline closes submissions without requiring a scheduled task."""
        from django.utils import timezone
        return (self.is_active and self.phase in ('registration', 'submission')
                and (not self.submission_deadline or timezone.now() <= self.submission_deadline))


class Team(models.Model):
    """A season-scoped team. The invitation secret is stored only as a hash."""
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=80)
    contact_email = models.EmailField(blank=True)
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
    STATUS_CHOICES = [('registered', 'Đã đăng ký'), ('locked', 'Đã khóa'), ('withdrawn', 'Rút'), ('disqualified', 'Bị loại')]
    exclusion_reason = models.TextField(blank=True)
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


class OfficialBot(models.Model):
    entry = models.OneToOneField(CompetitionEntry, on_delete=models.PROTECT, related_name='official_bot')
    submission = models.ForeignKey('submissions.Submission', on_delete=models.PROTECT)
    source_code = models.TextField()
    sha256 = models.CharField(max_length=64)
    frozen_at = models.DateTimeField(null=True, blank=True)


class JudgeWorker(models.Model):
    slot = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=80)
    token_hash = models.CharField(max_length=64, unique=True)
    enabled = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(slot__gte=1, slot__lte=4), name='four_judge_slots')]


class JudgingJob(models.Model):
    KINDS = [('validation', 'Kiểm tra bài'), ('fixture', 'Thi đấu')]
    STATES = [('queued', 'Đang chờ'), ('running', 'Đang chấm'), ('completed', 'Hoàn thành'), ('failed', 'Lỗi hạ tầng'), ('review', 'Cần trọng tài')]
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='judging_jobs')
    kind = models.CharField(max_length=12, choices=KINDS)
    bot = models.OneToOneField(OfficialBot, null=True, blank=True, on_delete=models.PROTECT, related_name='validation_job')
    fixture = models.OneToOneField(TournamentFixture, null=True, blank=True, on_delete=models.PROTECT, related_name='judging_job')
    state = models.CharField(max_length=12, choices=STATES, default='queued', db_index=True)
    worker = models.ForeignKey(JudgeWorker, null=True, blank=True, on_delete=models.PROTECT)
    lease_token = models.CharField(max_length=64, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['season', 'kind', 'state'])]
        constraints = [models.CheckConstraint(condition=(Q(kind='validation', bot__isnull=False, fixture__isnull=True) | Q(kind='fixture', bot__isnull=True, fixture__isnull=False)), name='job_has_one_target')]
        permissions = [('operate_tournament', 'Điều hành giải'), ('referee_tournament', 'Xử lý khiếu nại')]


class PracticeMatch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='practice_matches')
    request_id = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    submission = models.ForeignKey('submissions.Submission', null=True, on_delete=models.SET_NULL, related_name='practice_as_owner')
    opponent = models.ForeignKey('submissions.Submission', null=True, blank=True, on_delete=models.SET_NULL, related_name='practice_as_opponent')
    own_label = models.CharField(max_length=220)
    opponent_label = models.CharField(max_length=220)
    opponent_key = models.CharField(max_length=80)
    own_source = models.TextField()
    opponent_source = models.TextField()
    player_side = models.CharField(max_length=2, choices=[('P1', 'P1'), ('P2', 'P2')], default='P1')
    image = models.CharField(max_length=150)
    engine = models.CharField(max_length=64)
    state = models.CharField(max_length=12, choices=[('queued','Chờ máy chấm'),('running','Đang đấu'),('completed','Hoàn thành'),('failed','Lỗi máy chấm'),('cancelled','Đã hủy')], default='queued')
    worker = models.ForeignKey(JudgeWorker, null=True, blank=True, on_delete=models.SET_NULL)
    lease_token = models.CharField(max_length=64, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(default=dict)
    message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','request_id'], name='practice_request_once')]
        indexes = [models.Index(fields=['user','-created_at'], name='practice_owner_recent'),
                   models.Index(fields=['state','created_at'], name='practice_queue_order')]


class TournamentAudit(models.Model):
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='audit_events')
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class TournamentNotice(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='notices')
    title = models.CharField(max_length=160)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class TournamentEmail(models.Model):
    notice = models.ForeignKey(TournamentNotice, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['notice', 'user'], name='one_notice_email_per_user')]


class TournamentAppeal(models.Model):
    fixture = models.ForeignKey(TournamentFixture, on_delete=models.PROTECT, related_name='appeals')
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    message = models.TextField()
    evidence = models.TextField(blank=True)
    decision = models.TextField(blank=True)
    resolved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='resolved_appeals')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class VerifiedContact(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    email = models.EmailField()
    verified_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)


class ContactEmailClaim(models.Model):
    """Serializes email ownership across personal and captain-managed team contacts."""
    email = models.CharField(max_length=254, unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contact_email_claims')


class TournamentWaitlist(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['season', 'user'], name='one_waitlist_per_user')]
