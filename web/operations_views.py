import csv
import hashlib
import io
import threading

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from submissions.models import Submission
from .models import (Season, CompetitionEntry, OfficialBot, JudgeWorker, JudgingJob,
                     TournamentFixture, TournamentGroup, TournamentNotice, TournamentWaitlist, UserProfile)
from . import tournament_ops as ops


def usage_guide(request):
    role = 'admin' if ops.can_operate(request.user) else 'user'
    return render(request, 'web/usage_guide.html', {
        'page': 'guide', 'guide_role': role,
        'is_guest': request.session.get('is_guest', False),
    })


@login_required(login_url='/login/')
@ensure_csrf_cookie
def dashboard(request):
    preferred = CompetitionEntry.objects.filter(user=request.user).exclude(status='withdrawn').order_by('-season__created_at').values_list('season_id', flat=True).first()
    return render(request, 'web/tournament_operations.html', {'page': 'competition',
        'operator': ops.can_operate(request.user),
        'preferred_season_id': preferred,
        'seasons': Season.objects.all().only('id', 'name')})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_season(request):
    if not ops.can_operate(request.user):
        return Response(status=403)
    name = str(request.data.get('name', '')).strip()
    if not name or len(name) > 120:
        return Response({'error': 'Tên mùa giải cần từ 1 đến 120 ký tự.'}, status=400)
    statement = str(request.data.get('problem_statement', '')).strip()
    raw_deadline = request.data.get('submission_deadline', '')
    deadline = parse_datetime(raw_deadline) if raw_deadline else None
    if raw_deadline and deadline is None:
        return Response({'error': 'Thời hạn nộp phải là ngày giờ hợp lệ.'}, status=400)
    if deadline and timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline)
    from django.conf import settings
    season = Season.objects.create(
        name=name, description=str(request.data.get('description', '')).strip(),
        problem_statement=statement, submission_deadline=deadline,
        judge_image=settings.TOURNAMENT_DOCKER_IMAGE, entry_mode='individual',
        phase='submission', start_date=timezone.localdate(), created_by=request.user,
    )
    ops.audit(season, request.user, 'create_season')
    return Response({'id': season.pk, 'name': season.name}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    if request.session.get('is_guest'):
        return Response(status=403)
    student_id = str(request.data.get('student_id', '')).strip()
    class_name = str(request.data.get('class_name', '')).strip()
    if len(student_id) > 40 or len(class_name) > 80:
        return Response({'error': 'Mã sinh viên tối đa 40 ký tự, lớp tối đa 80 ký tự.'}, status=400)
    UserProfile.objects.update_or_create(user=request.user, defaults={'student_id': student_id, 'class_name': class_name})
    return Response({'ok': True})


def _error(exc):
    return Response({'error': str(exc)}, status=409)


def _mine(user, season):
    return CompetitionEntry.objects.filter(season=season, user=user)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def overview(request, season_id):
    season = get_object_or_404(Season, pk=season_id)
    operator = ops.can_operate(request.user)
    mine = _mine(request.user, season)
    jobs = season.judging_jobs.all()
    if not operator:
        jobs = jobs.filter(Q(bot__entry__in=mine) | Q(fixture__entry1__in=mine) | Q(fixture__entry2__in=mine))
    job_rows = []
    for job in jobs.order_by('-pk').values('id', 'kind', 'state', 'worker__slot', 'bot_id', 'bot__entry__display_name',
            'fixture_id', 'fixture__entry1__display_name', 'fixture__entry2__display_name', 'attempts',
            'result__valid', 'result__message', 'finished_at')[:100]:
        # Results may contain Python stderr; visible only to entrants or operators.
        job_rows.append({'id': job['id'], 'kind': job['kind'], 'state': job['state'], 'worker': job['worker__slot'],
                         'entry': job['bot__entry__display_name'] if job['bot_id'] else f"{job['fixture__entry1__display_name']} / {job['fixture__entry2__display_name']}",
                         'attempts': job['attempts'], 'valid': job['result__valid'],
                         'message': str(job['result__message'] or '')[:2000], 'fixture_id': job['fixture_id'],
                         'finished_at': job['finished_at']})
    entries = []
    for entry in mine.select_related('team__captain', 'official_bot__submission'):
        bot = getattr(entry, 'official_bot', None)
        entries.append({'id': entry.pk, 'name': entry.display_name, 'status': entry.status,
                        'exclusion_reason': entry.exclusion_reason,
                        'captain': ops.owns_entry(request.user, entry, captain=True),
                        'selected': bot.submission_id if bot else None, 'hash': bot.sha256 if bot else '',
                        'frozen': bool(bot and bot.frozen_at),
                        'submissions': list(entry.submissions.order_by('-submitted_at').values('id', 'ai_name', 'version')[:50])})
    public = ops.public_status(season)
    data = {'id': season.pk, 'name': season.name, 'description': season.description,
            'problem_statement': season.problem_statement, 'submissions_open': season.submissions_open,
            'phase': season.phase, 'phase_label': season.get_phase_display(),
            'drawn': bool(season.drawn_at),
            **public, 'capacity': min(season.max_participants, 4000),
            'paused': season.judging_paused,
            'registration_deadline': season.registration_deadline, 'submission_deadline': season.submission_deadline,
            'entries': entries, 'jobs': job_rows,
            'notices': list(season.notices.order_by('-pk').values('title', 'body', 'created_at')[:20]),
            'profile': {'student_id': request.user.profile.student_id, 'class_name': request.user.profile.class_name},
            'operator': operator, 'provisional': season.phase != 'completed'}
    if operator:
        data['audit'] = list(season.audit_events.order_by('-pk').values('action', 'actor__username', 'detail', 'created_at')[:50])
        data['judge_image'] = season.judge_image
        data['waitlist'] = list(TournamentWaitlist.objects.filter(season=season).order_by('pk').values('user_id', 'user__username', 'created_at')[:100])
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def choose_bot(request, entry_id):
    entry = get_object_or_404(CompetitionEntry, pk=entry_id)
    submission = get_object_or_404(Submission, pk=request.data.get('submission_id'), competition_entry=entry)
    try:
        bot = ops.select_bot(entry.pk, submission, request.user)
    except ValueError as exc:
        return _error(exc)
    return Response({'sha256': bot.sha256})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def operate(request, season_id):
    if not ops.can_operate(request.user):
        return Response({'error': 'Bạn không có quyền điều hành giải.'}, status=403)
    action = request.data.get('action')
    completion_message = ''
    try:
        with transaction.atomic():
            season = get_object_or_404(Season.objects.select_for_update(), pk=season_id)
            if action == 'configure':
                if season.phase not in ('registration', 'submission'):
                    raise ValueError('Cấu hình đã khóa.')
                capacity = int(request.data.get('capacity', season.max_participants))
                if not ops.participant_count(season) <= capacity <= 4000 or capacity < 2:
                    raise ValueError('Giới hạn từ số người hiện tại đến 4000, tối thiểu 2.')
                season.max_participants = capacity
                for field in ['name', 'description', 'problem_statement']:
                    if field in request.data:
                        value = str(request.data[field]).strip()
                        if field == 'name' and (not value or len(value) > 120):
                            raise ValueError('Tên giải cần từ 1 đến 120 ký tự.')
                        setattr(season, field, value)
                for field in ['submission_deadline']:
                    if field in request.data:
                        raw = request.data[field]
                        value = parse_datetime(raw) if raw else None
                        if raw and value is None:
                            raise ValueError('Thời hạn phải là ngày giờ ISO hợp lệ.')
                        if value and timezone.is_naive(value):
                            value = timezone.make_aware(value)
                        setattr(season, field, value)
                season.save()
                ops.audit(season, request.user, 'configure', capacity=capacity)
            elif action == 'close_submissions':
                if season.phase not in ('registration', 'submission'):
                    raise ValueError('Giải không còn ở giai đoạn nhận bài.')
                season.phase = 'locked'
                season.submission_deadline = timezone.now()
                season.entries.filter(status='registered').update(status='locked')
                OfficialBot.objects.filter(entry__season=season).update(frozen_at=timezone.now())
                season.save(update_fields=['phase', 'submission_deadline'])
                ops.audit(season, request.user, 'close_submissions')
            elif action == 'phase':
                ops.transition(season.pk, request.data.get('phase'), request.user)
            elif action == 'validate':
                ops.enqueue_validation(season.pk, request.user)
            elif action == 'reopen':
                ops.reopen_submissions(season.pk, request.user, str(request.data.get('reason', '')))
            elif action == 'queue':
                ops.queue_matches(season.pk, request.user)
            elif action == 'start_tournament':
                # The only operational button: close, validate, draw and queue.
                if season.phase in ('registration', 'submission'):
                    season.phase = 'locked'
                    season.submission_deadline = timezone.now()
                    season.entries.filter(status='registered').update(status='locked')
                    OfficialBot.objects.filter(entry__season=season).update(frozen_at=timezone.now())
                    season.save(update_fields=['phase', 'submission_deadline'])
                if season.phase == 'locked':
                    ops.enqueue_validation(season.pk, request.user)
                    # A previous click may have started the job while Docker was
                    # unavailable. Let the same button retry it after the host is fixed.
                    season.judging_jobs.filter(kind='validation', state='failed').update(
                        state='queued', worker=None, lease_token='', lease_until=None,
                        attempts=0, result={}, finished_at=None,
                    )
                    pending = season.judging_jobs.filter(kind='validation').exclude(state='completed', result__valid=True)
                    if pending.exists():
                        completion_message = 'Đang kiểm tra bot trong sandbox. Bấm “Chạy giải” lại khi tất cả bài đã đạt.'
                        if settings.LOCAL_JUDGE_AUTOSTART:
                            transaction.on_commit(lambda: threading.Thread(
                                target=__import__('web.local_judge', fromlist=['run_until_empty']).run_until_empty,
                                daemon=True,
                            ).start())
                    else:
                        if not season.drawn_at:
                            from .tournament import draw_season
                            draw_season(season.pk)
                        ops.transition(season.pk, 'running', request.user)
                if season.phase == 'running':
                    ops.queue_matches(season.pk, request.user)
                    if settings.LOCAL_JUDGE_AUTOSTART:
                        # Start only after this transaction commits, so the runner
                        # can see the newly queued matches.
                        transaction.on_commit(lambda: threading.Thread(
                            target=__import__('web.local_judge', fromlist=['run_until_empty']).run_until_empty,
                            daemon=True,
                        ).start())
            elif action == 'pause':
                season.judging_paused = not season.judging_paused
                season.save(update_fields=['judging_paused'])
                ops.audit(season, request.user, 'pause', paused=season.judging_paused)
            elif action == 'draw':
                if season.phase != 'locked':
                    raise ValueError('Khóa bài trước khi bốc thăm.')
                from .tournament import draw_season
                draw_season(season.pk)
                ops.audit(season, request.user, 'draw')
            elif action == 'notice':
                title, body = str(request.data.get('title', '')).strip(), str(request.data.get('body', '')).strip()
                if not title or not body or len(title) > 160 or len(body) > 10000:
                    raise ValueError('Nhập tiêu đề và nội dung thông báo hợp lệ.')
                TournamentNotice.objects.create(season=season, title=title, body=body)
                ops.audit(season, request.user, 'notice', title=title)
            elif action == 'disqualify':
                if season.drawn_at or season.phase not in ('registration', 'submission', 'locked'):
                    raise ValueError('Chỉ loại mục dự thi trước khi bốc thăm.')
                entry = get_object_or_404(CompetitionEntry, pk=request.data.get('entry_id'), season=season)
                reason = str(request.data.get('reason', '')).strip()
                if not reason or season.judging_jobs.filter(bot__entry=entry, state='running').exists():
                    raise ValueError('Cần lý do và chờ tác vụ đang chạy hoàn tất.')
                season.judging_jobs.filter(bot__entry=entry).delete()
                entry.status, entry.exclusion_reason = 'disqualified', reason
                entry.save(update_fields=['status', 'exclusion_reason'])
                ops.audit(season, request.user, 'disqualify', entry=entry.pk, reason=reason)
            elif action == 'promote':
                from django.contrib.auth import get_user_model
                from .competition_views import _registration_open, _capacity_error
                if not _registration_open(season):
                    raise ValueError('Giải hiện không nhận đăng ký mới.')
                item = get_object_or_404(TournamentWaitlist, season=season, user_id=request.data.get('user_id'))
                user = get_user_model().objects.select_for_update().get(pk=item.user_id)
                if season.entries.filter(user=user).exists():
                    raise ValueError('Tài khoản này đã có mục dự thi.')
                error = _capacity_error(season, user)
                if error:
                    raise ValueError(error)
                CompetitionEntry.objects.create(season=season, user=user, display_name=user.username)
                item.delete()
                ops.audit(season, request.user, 'promote_waitlist', user=user.pk)
            else:
                raise ValueError('Thao tác không hợp lệ.')
    except (ValueError, TypeError) as exc:
        return _error(exc)
    return Response({'ok': True, 'message': completion_message})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def retry(request, job_id):
    if not ops.can_operate(request.user):
        return Response(status=403)
    get_object_or_404(JudgingJob, pk=job_id)
    try:
        ops.retry_job(job_id, request.user, str(request.data.get('reason', '')))
    except ValueError as exc:
        return _error(exc)
    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def preflight(request, entry_id):
    with transaction.atomic():
        original = get_object_or_404(CompetitionEntry, pk=entry_id)
        season = Season.objects.select_for_update().get(pk=original.season_id)
        entry = CompetitionEntry.objects.select_related('team').get(pk=entry_id)
        if request.session.get('is_guest') or not ops.owns_entry(request.user, entry, captain=True):
            return Response(status=403)
        if season.phase not in ('registration', 'submission') or entry.status != 'registered':
            return _error(ValueError('Chỉ kiểm tra thử trước khi khóa bài.'))
        bot = get_object_or_404(OfficialBot, entry=entry)
        try:
            ops.ensure_image(season)
            from matches.tournament import engine_hash
            if season.judge_engine and season.judge_engine != engine_hash():
                raise ValueError('Engine đã khóa không khớp release hiện tại.')
            if not season.judge_engine:
                season.judge_engine = engine_hash()
                season.save(update_fields=['judge_engine'])
            if season.audit_events.filter(actor=request.user, action='preflight', created_at__date=timezone.localdate()).count() >= 5:
                return Response({'error': 'Tối đa 5 lượt kiểm tra thử mỗi ngày trong mùa giải.'}, status=429)
            previous = JudgingJob.objects.filter(bot=bot).first()
            if previous and previous.state in ('running', 'queued'):
                return Response({'id': previous.pk})
            if previous:
                ops.audit(season, request.user, 'previous_preflight', result=previous.result, bot=bot.pk)
                previous.delete()
            job = JudgingJob.objects.create(bot=bot, kind='validation', season=season)
            ops.audit(season, request.user, 'preflight', job=job.pk)
        except ValueError as exc:
            return _error(exc)
    return Response({'id': job.pk})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def replay(request, job_id):
    job = get_object_or_404(JudgingJob.objects.select_related('fixture__entry1__team', 'fixture__entry2__team'), pk=job_id, kind='fixture')
    if not ops.can_operate(request.user) and job.season.phase != 'completed' and not (ops.owns_entry(request.user, job.fixture.entry1) or ops.owns_entry(request.user, job.fixture.entry2)):
        return Response(status=403)
    return Response(job.result)






@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fixtures(request, season_id):
    from django.core.paginator import Paginator
    season = get_object_or_404(Season, pk=season_id)
    queryset = TournamentFixture.objects.filter(tournament_round__season=season).order_by('tournament_round__order', 'match_number').values(
        'id', 'tournament_round__name', 'group__code', 'entry1__display_name', 'entry2__display_name', 'result',
        'entry1__user_id', 'entry2__user_id', 'judging_job__id', 'judging_job__state')
    paginator = Paginator(queryset, 50)
    page = paginator.get_page(request.query_params.get('page', 1))
    rows = list(page)
    for row in rows:
        row['can_view_replay'] = bool(row['judging_job__id'] and row['judging_job__state'] in ('completed', 'review') and
            (season.phase == 'completed' or ops.can_operate(request.user) or request.user.pk in (row['entry1__user_id'], row['entry2__user_id'])))
        del row['entry1__user_id'], row['entry2__user_id']
    return Response({'fixtures': rows, 'pages': paginator.num_pages, 'total': paginator.count, 'provisional': season.phase != 'completed'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def standings(request, season_id):
    from django.core.paginator import Paginator
    from .tournament import group_standings
    season = get_object_or_404(Season, pk=season_id)
    queryset = TournamentGroup.objects.filter(tournament_round__season=season).select_related('tournament_round__season').prefetch_related('entries', 'fixtures').order_by('draw_order')
    paginator = Paginator(queryset, 20)
    page = paginator.get_page(request.query_params.get('page', 1))
    groups = [{'code': group.code, 'rows': [{'name': row['entry'].display_name, **{key: row[key] for key in ['rank', 'played', 'wins', 'draws', 'losses', 'points']}} for row in group_standings(group)]} for group in page]
    return Response({'groups': groups, 'pages': paginator.num_pages, 'provisional': season.phase != 'completed'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def adjudicate(request, job_id):
    if not ops.can_operate(request.user):
        return Response(status=403)
    from .tournament import record_fixture_result
    original = get_object_or_404(JudgingJob, pk=job_id)
    try:
        with transaction.atomic():
            season = Season.objects.select_for_update().get(pk=original.season_id)
            job = JudgingJob.objects.select_for_update().get(pk=job_id)
            reason = str(request.data.get('reason', '')).strip()
            outcome = request.data.get('result')
            if job.state != 'review' or outcome not in ('entry1_win', 'entry2_win') or not reason or season.phase != 'running':
                raise ValueError('Cần trận chờ trọng tài, kết quả phân thắng thua và lý do.')
            record_fixture_result(job.fixture_id, outcome)
            ops.audit(season, request.user, 'adjudicate', job=job.pk, reason=reason, outcome=outcome, replay=job.result)
            job.state = 'completed'
            job.result = {**job.result, 'adjudication': {'reason': reason, 'outcome': outcome}}
            job.save(update_fields=['state', 'result'])
            ops.queue_ready_fixtures(season)
    except ValueError as exc:
        return _error(exc)
    return Response({'ok': True})




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def waitlist(request, season_id):
    season = get_object_or_404(Season, pk=season_id)
    from .competition_views import _registration_open
    if request.session.get('is_guest') or ops.can_operate(request.user) or not _registration_open(season):
        return Response(status=403)
    item, _ = TournamentWaitlist.objects.get_or_create(season=season, user=request.user)
    return Response({'position': TournamentWaitlist.objects.filter(season=season, pk__lte=item.pk).count()})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def withdraw(request, entry_id):
    with transaction.atomic():
        original = get_object_or_404(CompetitionEntry, pk=entry_id)
        season = Season.objects.select_for_update().get(pk=original.season_id)
        entry = CompetitionEntry.objects.select_for_update().get(pk=entry_id)
        if not ops.owns_entry(request.user, entry, captain=True):
            return Response(status=403)
        if season.phase not in ('registration', 'submission') or season.drawn_at or entry.status != 'registered':
            return _error(ValueError('Không thể rút sau khi khóa/bốc thăm.'))
        if season.judging_jobs.filter(Q(bot__entry=entry), state='running').exists():
            return _error(ValueError('Đợi kiểm tra bài hoàn tất trước khi rút.'))
        entry.status = 'withdrawn'
        entry.save(update_fields=['status'])
        season.judging_jobs.filter(bot__entry=entry).delete()
        ops.audit(season, request.user, 'withdraw', entry=entry.pk)
    return Response({'ok': True})


def _csv_safe(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def roster(request, season_id):
    if not ops.can_operate(request.user):
        return Response(status=403)
    season = get_object_or_404(Season, pk=season_id)
    if request.method == 'POST':
        # CSV imports use the same locked registration path as user registration.
        from django.contrib.auth import get_user_model
        from .competition_views import _registration_open, _capacity_error
        text = str(request.data.get('csv', ''))
        if len(text) > 1_000_000:
            return Response(status=413)
        try:
            with transaction.atomic():
                season = Season.objects.select_for_update().get(pk=season_id)
                if not _registration_open(season):
                    raise ValueError('Giải hiện không nhận đăng ký mới.')
                count = 0
                for row in csv.DictReader(io.StringIO(text)):
                    user = get_user_model().objects.get(username=row['username'])
                    if ops.can_operate(user):
                        raise ValueError(f'{user.username} là tài khoản admin, không phải đại diện dự thi.')
                    if season.entries.filter(user=user).exists():
                        continue
                    error = _capacity_error(season, user)
                    if error:
                        raise ValueError(error)
                    CompetitionEntry.objects.create(season=season, user=user, display_name=user.username)
                    count += 1
                ops.audit(season, request.user, 'import_roster', count=count)
        except (ValueError, KeyError, get_user_model().DoesNotExist) as exc:
            return _error(exc)
        return Response({'imported': count})
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="season-{season.pk}-roster.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['entry_id', 'name', 'status', 'representative', 'student_id', 'class_name'])
    for entry in season.entries.select_related('user__profile'):
        users = [entry.user] if entry.user_id else []
        for user in users:
            profile = getattr(user, 'profile', None)
            writer.writerow([entry.pk, _csv_safe(entry.display_name), entry.status, _csv_safe(user.username),
                             _csv_safe(profile.student_id if profile else ''), _csv_safe(profile.class_name if profile else '')])
    return response


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def worker_api(request, action):
    header = request.headers.get('Authorization', '')
    token = header[7:] if header.startswith('Bearer ') else ''
    worker = JudgeWorker.objects.filter(token_hash=hashlib.sha256(token.encode()).hexdigest(), enabled=True).first() if token else None
    if not worker:
        return Response({'error': 'Máy chấm chưa được xác thực.'}, status=403)
    from . import practice_ops
    from .models import PracticeMatch
    try:
        if action == 'claim':
            job = practice_ops.claim(worker.pk, request.data.get('engine'))
            return Response({'job': job})
        if str(request.data.get('job_id','')).startswith('practice-'):
            if action not in ('heartbeat','finish'):
                return Response(status=404)
            practice_ops.update(worker,request.data.get('job_id'),request.data.get('lease_token'),
                                request.data.get('result'),heartbeat=action=='heartbeat')
            return Response({'ok':True})
        if action == 'heartbeat':
            ops.heartbeat(worker, request.data.get('job_id'), request.data.get('lease_token'))
        elif action == 'finish':
            ops.finish_job(worker, request.data.get('job_id'), request.data.get('lease_token'), request.data.get('result'))
        else:
            return Response(status=404)
    except (ValueError, JudgingJob.DoesNotExist, JudgeWorker.DoesNotExist, PracticeMatch.DoesNotExist) as exc:
        return _error(exc)
    return Response({'ok': True})
