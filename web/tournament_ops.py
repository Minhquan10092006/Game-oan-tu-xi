"""Durable coordinator. Untrusted Python is executed only on remote Docker workers."""
from datetime import timedelta
import hashlib
import re
import secrets

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from matches.tournament import engine_hash
from .models import (Season, CompetitionEntry, OfficialBot, JudgingJob,
                     JudgeWorker, TournamentAudit, TournamentNotice, TournamentFixture)

LEASE_SECONDS = 120
MAX_ATTEMPTS = 3


def can_operate(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.has_perm('web.operate_tournament'))


def can_referee(user):
    return can_operate(user) or (user.is_authenticated and user.has_perm('web.referee_tournament'))


def audit(season, actor, action, **detail):
    TournamentAudit.objects.create(season=season, actor=actor, action=action, detail=detail)


def participant_count(season):
    return CompetitionEntry.objects.filter(season=season, status__in=['registered', 'locked']).count()


def owns_entry(user, entry, captain=False):
    if entry.user_id:
        return entry.user_id == user.pk
    # Historical entries keep their representative until the data migration is applied.
    return bool(entry.team_id and entry.team.captain_id == user.pk)


@transaction.atomic
def select_bot(entry_id, submission, actor):
    season = Season.objects.select_for_update().get(pk=submission.competition_entry.season_id)
    entry = CompetitionEntry.objects.select_for_update().get(pk=entry_id, season=season)
    if submission.competition_entry_id != entry.pk or not owns_entry(actor, entry, captain=True):
        raise ValueError('Chỉ tài khoản đại diện của mục dự thi được chọn phiên bản chính thức.')
    if entry.status != 'registered' or season.phase not in ('registration', 'submission'):
        raise ValueError('Đã khóa phiên bản chính thức.')
    if season.submission_deadline and timezone.now() > season.submission_deadline:
        raise ValueError('Đã hết hạn chọn bài.')
    existing = OfficialBot.objects.filter(entry=entry).first()
    if existing and JudgingJob.objects.filter(bot=existing, state='running').exists():
        raise ValueError('Bài đang được kiểm tra; hãy chờ hoàn tất trước khi đổi phiên bản.')
    if existing:
        previous = JudgingJob.objects.filter(bot=existing).first()
        audit(season, actor, 'replace_bot', entry=entry.pk, previous_submission=existing.submission_id,
              previous_sha256=existing.sha256, previous_report=previous.result if previous else {})
        JudgingJob.objects.filter(bot=existing).delete()
    bot, _ = OfficialBot.objects.update_or_create(entry=entry, defaults={
        'submission': submission, 'source_code': submission.source_code, 'sha256': submission.source_sha256,
    })
    audit(season, actor, 'select_bot', entry=entry.pk, submission=submission.pk, sha256=bot.sha256)
    return bot


def ensure_image(season):
    # The judge runs locally with the named sandbox image. Keeping this a plain
    # image name removes image hashes from the admin workflow.
    if not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9._-]+)?', season.judge_image or ''):
        raise ValueError('Môi trường sandbox chưa sẵn sàng trên server.')


@transaction.atomic
def enqueue_validation(season_id, actor):
    season = Season.objects.select_for_update().get(pk=season_id)
    ensure_image(season)
    if not season.judge_engine:
        season.judge_engine = engine_hash()
        season.save(update_fields=['judge_engine'])
    elif season.judge_engine != engine_hash():
        # A failed infrastructure-only preflight has produced no judged result.
        # Allow it to resume on the current code; keep the lock once any draw,
        # fixture, running job, or successful validation exists.
        has_fixture_work = season.judging_jobs.filter(kind='fixture').exists()
        has_running_work = season.judging_jobs.filter(state='running').exists()
        has_successful_validation = season.judging_jobs.filter(
            kind='validation', state='completed', result__valid=True,
        ).exists()
        has_validation_queued = season.judging_jobs.filter(kind='validation', state='queued').exists()
        if season.drawn_at or has_fixture_work or has_running_work or has_successful_validation or has_validation_queued:
            raise ValueError('Engine đã đổi sau khi giải bắt đầu; không thể tiếp tục với phiên bản code khác.')
        season.judge_engine = engine_hash()
        season.save(update_fields=['judge_engine'])
        audit(season, actor, 'refresh_engine_after_infrastructure_failure')
    if season.phase not in ('registration', 'submission', 'locked'):
        raise ValueError('Chỉ kiểm tra bài trước khi bắt đầu thi đấu.')
    count = 0
    for bot in OfficialBot.objects.filter(entry__season=season, entry__status__in=['registered', 'locked']):
        _, created = JudgingJob.objects.get_or_create(bot=bot, defaults={'season': season, 'kind': 'validation'})
        count += created
    audit(season, actor, 'queue_validation', count=count)
    return count


@transaction.atomic
def transition(season_id, phase, actor):
    season = Season.objects.select_for_update().get(pk=season_id)
    allowed = {'registration': 'submission', 'submission': 'locked', 'locked': 'running',
               'running': 'completed'}
    if allowed.get(season.phase) != phase:
        raise ValueError('Chuyển giai đoạn theo thứ tự: đăng ký → nộp bài → khóa → thi đấu → kết thúc.')
    if phase == 'locked':
        entries = season.entries.filter(status__in=['registered', 'locked'])
        bots = OfficialBot.objects.filter(entry__in=entries)
        if not entries.exists() or entries.count() != bots.count():
            raise ValueError('Mỗi mục dự thi phải chọn một phiên bản chính thức trước khi khóa.')
        bots.update(frozen_at=timezone.now())
        entries.update(status='locked')
    if phase == 'running':
        bots = OfficialBot.objects.filter(entry__season=season, entry__status='locked')
        if not season.drawn_at or bots.exclude(validation_job__state='completed', validation_job__result__valid=True).exists():
            raise ValueError('Cần bốc thăm và tất cả bài chính thức vượt kiểm tra trước khi thi đấu.')
        ensure_image(season)
    if phase == 'completed' and (season.judging_jobs.filter(state__in=['queued', 'running', 'failed', 'review']).exists()
                              or TournamentFixture.objects.filter(tournament_round__season=season, result='scheduled').exists()):
        raise ValueError('Còn trận hoặc tác vụ chưa xử lý xong.')
    previous = season.phase
    season.phase = phase
    season.save(update_fields=['phase'])
    audit(season, actor, 'phase', previous=previous, phase=phase)
    TournamentNotice.objects.create(season=season, title='Cập nhật giai đoạn giải đấu', body=season.get_phase_display())


@transaction.atomic
def reopen_submissions(season_id, actor, reason):
    season = Season.objects.select_for_update().get(pk=season_id)
    if season.phase != 'locked' or not reason.strip() or season.judging_jobs.filter(state='running').exists():
        raise ValueError('Chỉ mở lại trước thi đấu, khi không có tác vụ đang chạy và phải có lý do.')
    season.phase = 'submission'
    season.save(update_fields=['phase'])
    season.entries.filter(status='locked').update(status='registered')
    OfficialBot.objects.filter(entry__season=season).update(frozen_at=None)
    audit(season, actor, 'reopen_submissions', reason=reason)
    TournamentNotice.objects.create(season=season, title='Mở lại nộp bài cho toàn giải', body=reason)


def queue_ready_fixtures(season):
    """Called while holding the season lock; newly resolved bracket slots enter the queue."""
    if season.phase != 'running':
        return 0
    fixtures = TournamentFixture.objects.filter(tournament_round__season=season, result='scheduled',
                                                entry1__isnull=False, entry2__isnull=False,
                                                judging_job__isnull=True)
    jobs = []
    for fixture in fixtures:
        if OfficialBot.objects.filter(entry_id__in=[fixture.entry1_id, fixture.entry2_id], frozen_at__isnull=False).count() == 2:
            jobs.append(JudgingJob(season=season, kind='fixture', fixture=fixture))
    JudgingJob.objects.bulk_create(jobs)
    return len(jobs)


@transaction.atomic
def queue_matches(season_id, actor):
    season = Season.objects.select_for_update().get(pk=season_id)
    if season.phase != 'running':
        raise ValueError('Mùa giải chưa ở giai đoạn thi đấu.')
    count = queue_ready_fixtures(season)
    audit(season, actor, 'queue_matches', count=count)
    return count


@transaction.atomic
def claim_job(worker_id, reported_engine):
    worker = JudgeWorker.objects.select_for_update().get(pk=worker_id, enabled=True)
    now = timezone.now()
    worker.last_seen = now
    worker.save(update_fields=['last_seen'])
    if reported_engine != engine_hash():
        raise ValueError('Phiên bản engine trên máy chấm không khớp web.')
    if JudgingJob.objects.filter(worker=worker, state='running', lease_until__gt=now).exists():
        return None
    # One season lock serializes scheduling/completion, including SQLite local development.
    seasons = Season.objects.filter(judging_paused=False, judging_jobs__state__in=['queued', 'running']).distinct().order_by('pk')
    for season_id in seasons.values_list('pk', flat=True):
        season = Season.objects.select_for_update().get(pk=season_id)
        if season.judging_paused:
            continue
        if season.judge_engine != reported_engine:
            raise ValueError('Engine mùa giải đã khóa không khớp; khôi phục đúng release.')
        expired = season.judging_jobs.filter(state='running', lease_until__lte=now)
        for job in expired:
            old_worker = job.worker_id
            job.state = 'failed' if job.attempts >= MAX_ATTEMPTS else 'queued'
            job.result = {'error': 'lease_expired', 'message': 'Máy chấm mất kết nối; chưa tính kết quả.'}
            job.worker = None
            job.lease_token = ''
            job.save()
            audit(season, None, 'lease_expired', job=job.pk, worker=old_worker, attempt=job.attempts)
        kinds = ['validation'] if season.phase in ('registration', 'submission', 'locked') else ['fixture'] if season.phase == 'running' else []
        job = season.judging_jobs.filter(state='queued', kind__in=kinds).order_by('pk').first()
        if not job:
            continue
        job.state, job.worker = 'running', worker
        job.lease_token = secrets.token_hex(32)
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.attempts += 1
        job.save()
        bots = [job.bot] if job.kind == 'validation' else [OfficialBot.objects.get(entry_id=job.fixture.entry1_id), OfficialBot.objects.get(entry_id=job.fixture.entry2_id)]
        audit(season, None, 'claim', job=job.pk, worker=worker.slot, attempt=job.attempts)
        return {'id': job.pk, 'kind': job.kind, 'lease_token': job.lease_token,
                'image': season.judge_image, 'engine': engine_hash(),
                'bots': [{'source': bot.source_code} for bot in bots]}
    return None


def locked_job(worker, job_id, token):
    JudgeWorker.objects.select_for_update().get(pk=worker.pk, enabled=True)
    original = JudgingJob.objects.get(pk=job_id)
    season = Season.objects.select_for_update().get(pk=original.season_id)
    job = JudgingJob.objects.select_for_update().get(pk=job_id)
    if season.judge_engine != engine_hash():
        raise ValueError('Engine đã đổi sau khi khóa; tạm dừng chấm và khôi phục release.')
    if job.worker_id != worker.pk or job.state != 'running' or not secrets.compare_digest(job.lease_token, str(token)) or job.lease_until <= timezone.now():
        raise ValueError('Lượt chấm đã hết hạn hoặc không thuộc máy này.')
    return season, job


@transaction.atomic
def heartbeat(worker, job_id, token):
    _, job = locked_job(worker, job_id, token)
    job.lease_until = timezone.now() + timedelta(seconds=LEASE_SECONDS)
    job.save(update_fields=['lease_until'])
    JudgeWorker.objects.filter(pk=worker.pk).update(last_seen=timezone.now())


@transaction.atomic
def finish_job(worker, job_id, token, result):
    season, job = locked_job(worker, job_id, token)
    if not isinstance(result, dict):
        raise ValueError('Kết quả không hợp lệ.')
    if result.get('infrastructure_error'):
        job.state = 'failed'
    elif job.kind == 'validation':
        if type(result.get('valid')) is not bool:
            raise ValueError('Thiếu kết quả kiểm tra bài.')
        job.state = 'completed'
    else:
        if result.get('result') not in ('win', 'forfeit', 'draw') or (result['result'] == 'draw' and result.get('winner') is not None) or (result['result'] != 'draw' and result.get('winner') not in ('P1', 'P2')):
            raise ValueError('Kết quả trận không hợp lệ.')
        if result.get('id') != f'job-{job.pk}':
            raise ValueError('Replay không khớp mã công việc.')
        from .tournament import record_fixture_result
        if result['result'] == 'draw' and job.fixture.group_id is None:
            # A knockout draw needs the published tie-break procedure, never a random winner.
            job.state = 'review'
        else:
            outcome = 'draw' if result['result'] == 'draw' else 'entry1_win' if result['winner'] == 'P1' else 'entry2_win'
            record_fixture_result(job.fixture_id, outcome)
            job.state = 'completed'
    job.result, job.finished_at = result, timezone.now()
    job.lease_until = None
    job.save()
    audit(season, None, 'finish', job=job.pk, worker=worker.slot, state=job.state)
    if job.state == 'completed' and job.kind == 'fixture':
        queue_ready_fixtures(season)
    return job


@transaction.atomic
def retry_job(job_id, actor, reason):
    original = JudgingJob.objects.get(pk=job_id)
    season = Season.objects.select_for_update().get(pk=original.season_id)
    job = JudgingJob.objects.select_for_update().get(pk=job_id)
    if job.state not in ('failed', 'review') or not reason.strip():
        raise ValueError('Chỉ chạy lại tác vụ lỗi/cần trọng tài và phải có lý do.')
    audit(season, actor, 'retry', job=job.pk, reason=reason, previous_result=job.result)
    job.state, job.worker, job.lease_token, job.lease_until = 'queued', None, '', None
    job.attempts, job.result, job.finished_at = 0, {}, None
    job.save()


def progress(season):
    counts = {(row['kind'], row['state']): row['count'] for row in season.judging_jobs.values('kind', 'state').annotate(count=Count('id'))}
    parts = {}
    for kind in ('validation', 'fixture'):
        values = {state: counts.get((kind, state), 0) for state, _ in JudgingJob.STATES}
        total = (CompetitionEntry.objects.filter(season=season, status__in=['registered', 'locked']).count() if kind == 'validation'
                 else TournamentFixture.objects.filter(tournament_round__season=season).exclude(result='bye').count())
        if kind == 'fixture':
            values['completed'] = TournamentFixture.objects.filter(tournament_round__season=season).exclude(result__in=['bye', 'scheduled']).count()
        else:
            values['passed'] = season.judging_jobs.filter(kind='validation', state='completed', result__valid=True).count()
        values.update(total=total, percent=round(values['completed'] * 100 / total, 1) if total else 0)
        parts[kind] = values
    return parts


def public_status(season):
    """Only public aggregates are cached; never cache a participant's jobs or source."""
    from django.core.cache import cache
    key = f'tournament-status-v1:{season.pk}'
    value = cache.get(key)
    if value is not None:
        return value
    now = timezone.now()
    current = dict(JudgingJob.objects.filter(state='running', lease_until__gt=now).values_list('worker_id', 'pk'))
    workers = [{'slot': worker.slot, 'name': worker.name, 'enabled': worker.enabled,
                'online': bool(worker.enabled and worker.last_seen and worker.last_seen > now - timedelta(seconds=90)),
                'job': current.get(worker.pk), 'last_seen': worker.last_seen}
               for worker in JudgeWorker.objects.order_by('slot')]
    value = {'workers': workers, 'progress': progress(season), 'participants': participant_count(season)}
    cache.set(key, value, timeout=5)
    return value
