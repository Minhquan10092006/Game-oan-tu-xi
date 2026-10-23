from __future__ import annotations
import json, uuid
import logging
import smtplib
from pathlib import Path
from django.conf import settings
from django.core.mail import send_mass_mail
from django.core.mail.message import BadHeaderError
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import (
    UserProfile, Season, MatchHistory, TournamentFixture, TournamentGroup,
    TournamentRound,
)
from .tournament import DrawError, draw_season, group_standings, record_fixture_result

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────

def _is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

def _ensure_profile(user):
    UserProfile.objects.get_or_create(user=user)


# ── auth wall ────────────────────────────────────────────────────────

def index(request):
    """Public competition landing page; authentication is a separate destination."""
    if request.method == 'POST':
        return account(request)  # Compatibility with existing sign-in forms.
    from matches.game_engine import board_presets
    pieces = {tuple(p['at']): p for p in board_presets()['classic_9x9']['initial_pieces']}
    symbols = {'rock': 'B', 'paper': 'Ba', 'scissors': 'K'}
    cells = []
    for row in range(1, 10):
        for col in range(1, 10):
            piece = pieces.get((row, col))
            cells.append({'owner': piece['owner'] if piece else '',
                          'symbol': symbols[piece['type']] if piece else '',
                          'goal': (row, col) in ((1, 1), (9, 9))})
    return render(request, 'web/index.html', {
        'hero_cells': cells, 'page': 'home', 'is_guest': request.session.get('is_guest', False),
        'active_season': Season.objects.filter(is_active=True).first(),
    })


@login_required(login_url='/login/')
def play(request):
    return render(request, 'web/play.html', {
        'authed': True, 'user': request.user, 'page': 'play',
        'is_guest': request.session.get('is_guest', False), 'is_admin': _is_admin(request.user),
        'active_season': Season.objects.filter(is_active=True).first(),
    })


def account(request, mode='login'):
    """Dedicated sign-in/register pages with a same-origin return destination."""
    next_url = request.POST.get('next') or request.GET.get('next') or '/play/'
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = '/play/'
    is_guest = request.session.get('is_guest', False)
    active_season = Season.objects.filter(is_active=True).first()
    context = {
        'authed': request.user.is_authenticated,
        'user': request.user,
        'is_guest': is_guest,
        'is_admin': _is_admin(request.user),
        'active_season': active_season,
        'auth_error': '',
        'reg_errors': {},
        'auth_mode': mode,
        'page': mode,
        'next_url': next_url,
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'login':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user); _ensure_profile(user)
                request.session.pop('is_guest', None)
                return redirect(next_url)
            context['auth_error'] = 'Tên đăng nhập hoặc mật khẩu không đúng.'
            context['auth_mode'] = 'login'

        elif action == 'register':
            context['auth_mode'] = 'register'
            uname = request.POST.get('reg_username', '').strip()
            pw1   = request.POST.get('reg_password1', '')
            pw2   = request.POST.get('reg_password2', '')
            errs  = {}
            if not uname or not 3 <= len(uname) <= 150:
                errs['username'] = 'Tên đăng nhập cần từ 3 đến 150 ký tự.'
            elif User.objects.filter(username=uname).exists():
                errs['username'] = 'Tên đăng nhập đã tồn tại.'
            if len(pw1) < 6:
                errs['password1'] = 'Tối thiểu 6 ký tự.'
            elif pw1 != pw2:
                errs['password2'] = 'Hai mật khẩu không khớp.'
            if not errs:
                user = User.objects.create_user(username=uname, password=pw1)
                _ensure_profile(user); login(request, user)
                request.session.pop('is_guest', None)
                return redirect(next_url)
            context['reg_errors'] = errs

        elif action == 'guest':
            gname = f'guest_{uuid.uuid4().hex[:8]}'
            user  = User.objects.create_user(username=gname, password=uuid.uuid4().hex)
            _ensure_profile(user); login(request, user)
            request.session['is_guest'] = True
            return redirect(next_url)

    return render(request, 'web/account.html', context)


# ── logout ───────────────────────────────────────────────────────────

def logout_view(request):
    if request.session.get('is_guest') and request.user.is_authenticated:
        try: request.user.delete()
        except Exception: pass
    logout(request)
    return redirect('/')


# ── battlecode ───────────────────────────────────────────────────────

@login_required(login_url='/login/')
def battlecode_demo(request):
    active_season = Season.objects.filter(is_active=True).first()
    return render(request, 'web/battlecode_demo.html', {
        'page': 'play',
        'user': request.user,
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
        'active_season': active_season,
    })


# ── lịch sử ──────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def match_history(request):
    matches = MatchHistory.objects.filter(player=request.user).order_by('-played_at')
    return render(request, 'web/history.html', {
        'user': request.user, 'matches': matches, 'page': 'play',
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })


@login_required(login_url='/login/')
def match_detail(request, match_id):
    match = get_object_or_404(MatchHistory, match_id=match_id, player=request.user)
    return render(request, 'web/match_detail.html', {
        'user': request.user, 'match': match,
        'replay_json': json.dumps(match.get_replay()) if match.get_replay() else 'null',
        'is_admin': _is_admin(request.user),
    })


# ── mùa giải (admin) ─────────────────────────────────────────────────

@login_required(login_url='/login/')
def season_admin(request):
    if not _is_admin(request.user):
        return redirect('/')
    from submissions.models import Submission
    seasons = Season.objects.all()
    all_submissions = Submission.objects.select_related('submitter').order_by('-submitted_at')
    tournament_admin = []
    for season in seasons:
        group_round = season.rounds.filter(stage='group').first()
        groups = list(group_round.groups.order_by('draw_order')) if group_round else []
        tournament_admin.append({
            'season': season,
            'groups': [{
                'group': group,
                'standings': group_standings(group),
                'fixtures': group.fixtures.select_related('entry1', 'entry2').order_by('match_number'),
            } for group in groups],
            'knockout_rounds': season.rounds.exclude(
                stage__in=['group', 'third_place'],
            ).prefetch_related('fixtures__entry1', 'fixtures__entry2', 'fixtures__winner').order_by('order'),
            'third_place_round': season.rounds.filter(stage='third_place').prefetch_related(
                'fixtures__entry1', 'fixtures__entry2', 'fixtures__winner',
            ).first(),
        })
    return render(request, 'web/season_admin.html', {
        'user': request.user, 'seasons': seasons,
        'is_admin': True,
        'total_matches': MatchHistory.objects.count(),
        'total_users': User.objects.filter(is_staff=False).count(),
        'total_submissions': all_submissions.count(),
        'recent_matches': MatchHistory.objects.select_related('player','season').order_by('-played_at')[:20],
        'all_submissions': all_submissions[:50],
        'tournament_admin': tournament_admin,
    })


@login_required(login_url='/login/')
@require_POST
def season_create(request):
    if not _is_admin(request.user): return redirect('/')
    name = request.POST.get('name','').strip()
    if not name:
        messages.error(request, 'Tên mùa giải không được trống.')
        return redirect('/season-admin/')
    try:
        max_team_size = min(max(int(request.POST.get('max_team_size', 4) or 4), 2), 8)
    except (TypeError, ValueError):
        max_team_size = 4
    entry_mode = request.POST.get('entry_mode', 'both')
    if entry_mode not in {'individual', 'team', 'both'}:
        entry_mode = 'both'
    deadline_raw = request.POST.get('registration_deadline', '').strip()
    deadline = parse_datetime(deadline_raw) if deadline_raw else None
    if deadline_raw and deadline is None:
        messages.error(request, 'Hạn đăng ký không hợp lệ.')
        return redirect('/season-admin/')
    if deadline and timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline, timezone.get_current_timezone())
    season = Season.objects.create(
        name=name,
        description=request.POST.get('description','').strip(),
        start_date=request.POST.get('start_date') or timezone.now().date(),
        entry_mode=entry_mode,
        max_team_size=max_team_size,
        registration_deadline=deadline,
        is_active=True, created_by=request.user,
    )
    stages = [
        ('group', 'Vòng bảng', 'Hai lượt, tính điểm 3–1–0', 2),
        ('round_of_16', 'Vòng 16', 'Loại trực tiếp', 0),
        ('quarterfinal', 'Tứ kết', 'Loại trực tiếp', 0),
        ('semifinal', 'Bán kết', 'Loại trực tiếp', 0),
        ('third_place', 'Tranh hạng ba', 'Loại trực tiếp', 0),
        ('final', 'Chung kết', 'Loại trực tiếp', 0),
    ]
    TournamentRound.objects.bulk_create([
        TournamentRound(season=season, stage=stage, order=index, name=label,
                        format_note=note, advance_count=advance)
        for index, (stage, label, note, advance) in enumerate(stages, 1)
    ])
    messages.success(request, f'Đã tạo mùa giải "{name}".')
    return redirect('/season-admin/')


@login_required(login_url='/login/')
@require_POST
def season_toggle(request, pk):
    if not _is_admin(request.user): return redirect('/')
    s = get_object_or_404(Season, pk=pk)
    s.is_active = not s.is_active
    if not s.is_active and not s.end_date:
        s.end_date = timezone.now().date()
    s.save()
    messages.success(request, f'Mùa giải "{s.name}" {"kích hoạt" if s.is_active else "kết thúc"}.')
    return redirect('/season-admin/')


@login_required(login_url='/login/')
@require_POST
def season_delete(request, pk):
    if not _is_admin(request.user): return redirect('/')
    s = get_object_or_404(Season, pk=pk)
    name = s.name; s.delete()
    messages.success(request, f'Đã xoá "{name}".')
    return redirect('/season-admin/')


def _season_email_recipients(season):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(
        Q(individual_entries__season=season, individual_entries__status__in=['registered', 'locked'])
        | Q(team_memberships__team__season=season,
            team_memberships__team__entry__status__in=['registered', 'locked']),
        is_active=True,
    ).distinct().order_by('pk')


def _send_season_notification(season, subject, body_for_user):
    users = list(_season_email_recipients(season))
    recipients = [user for user in users if user.email.strip()]
    missing = [user.username for user in users if not user.email.strip()]
    if not recipients:
        return 0, len(missing), 'none'

    messages_to_send = [
        (subject, body_for_user(user), settings.DEFAULT_FROM_EMAIL, [user.email.strip()])
        for user in recipients
    ]
    sent = send_mass_mail(messages_to_send, fail_silently=False)
    backend = settings.EMAIL_BACKEND
    if backend.endswith('console.EmailBackend'):
        delivery = 'console'
    else:
        delivery = 'email'
    return sent, len(missing), delivery


def _draw_email_body(season, request):
    from .models import CompetitionEntry

    group_by_entry = {}
    for group in TournamentGroup.objects.filter(
        tournament_round__season=season,
    ).prefetch_related('entries'):
        for entry in group.entries.all():
            group_by_entry[entry.pk] = group.code

    users = list(_season_email_recipients(season))
    entry_by_user = {}
    for entry in CompetitionEntry.objects.filter(
        season=season, status='locked',
    ).select_related('team', 'user').prefetch_related('team__memberships__user'):
        if entry.user_id:
            entry_by_user[entry.user_id] = entry
        elif entry.team_id:
            for membership in entry.team.memberships.all():
                entry_by_user[membership.user_id] = entry

    destination = request.build_absolute_uri('/competition/')

    def body_for_user(user):
        entry = entry_by_user.get(user.pk)
        group = group_by_entry.get(entry.pk) if entry else None
        assignment = f'Bạn được xếp vào Bảng {group}.' if group else 'Hãy xem danh sách bảng trên website.'
        return (
            f'Xin chào {user.username},\n\n'
            f'Ban tổ chức đã bốc thăm mùa giải "{season.name}".\n'
            f'{assignment}\n'
            'Hai đơn vị đứng đầu mỗi bảng sẽ vào nhánh loại trực tiếp. '
            'Kết quả bảng và sơ đồ các vòng được cập nhật trực quan trên website.\n\n'
            f'Xem thông tin: {destination}\n'
        )

    return users, body_for_user


@login_required(login_url='/login/')
@require_POST
def season_draw(request, pk):
    if not _is_admin(request.user):
        return redirect('/')
    season = get_object_or_404(Season, pk=pk)
    try:
        result = draw_season(season.pk)
    except DrawError as exc:
        messages.error(request, str(exc))
        return redirect('/season-admin/')

    users, body_for_user = _draw_email_body(season, request)
    if not users:
        messages.warning(request, 'Bốc thăm đã lưu; chưa có thành viên để gửi email.')
        return redirect('/season-admin/')
    try:
        sent, missing, delivery = _send_season_notification(
            season, f'Đã bốc thăm mùa giải {season.name}',
            body_for_user,
        )
    except (BadHeaderError, OSError, smtplib.SMTPException) as exc:
        logger.exception('Draw email delivery failed for season %s', season.pk)
        messages.error(request, f'Bốc thăm đã lưu, nhưng gửi email bị lỗi: {exc}')
        return redirect('/season-admin/')

    summary = (
        f'Đã bốc thăm {result["entries"]} mục vào {result["group_count"]} bảng; '
        f'{result["qualifier_count"]} suất vào nhánh {result["bracket_size"]}, '
        f'{result["bye_count"]} suất miễn vòng đầu.'
    )
    if delivery == 'console':
        messages.warning(request, f'{summary} Email chỉ được ghi ra console local, chưa gửi ra hộp thư.')
    elif sent:
        messages.success(request, f'{summary} Đã gửi email cho {sent} thành viên.')
    else:
        messages.error(request, f'{summary} Hệ thống không gửi được email nào.')
    if missing:
        messages.warning(request, f'{missing} thành viên chưa có email hợp lệ; vui lòng bổ sung trước khi gửi lại thông báo.')
    return redirect('/season-admin/')


@login_required(login_url='/login/')
@require_POST
def season_email(request, pk):
    if not _is_admin(request.user):
        return redirect('/')
    season = get_object_or_404(Season, pk=pk)
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('body', '').strip()
    if not subject or len(subject) > 200 or not body or len(body) > 10000:
        messages.error(request, 'Nhập tiêu đề (tối đa 200 ký tự) và nội dung (tối đa 10.000 ký tự).')
        return redirect('/season-admin/')

    def body_for_user(user):
        return f'Xin chào {user.username},\n\n{body}\n'

    try:
        sent, missing, delivery = _send_season_notification(season, subject, body_for_user)
    except (BadHeaderError, OSError, smtplib.SMTPException) as exc:
        logger.exception('Season email delivery failed for season %s', season.pk)
        messages.error(request, f'Không gửi được email: {exc}')
        return redirect('/season-admin/')
    if delivery == 'none':
        messages.error(request, 'Chưa có thành viên nào có địa chỉ email; không gửi email nào.')
    elif delivery == 'console':
        messages.warning(request, f'Email của {sent} thành viên chỉ được ghi ra console local, chưa gửi ra hộp thư.')
    else:
        messages.success(request, f'Đã gửi email cho {sent} thành viên.')
    if missing:
        messages.warning(request, f'{missing} thành viên chưa có email hợp lệ.')
    return redirect('/season-admin/')


@login_required(login_url='/login/')
@require_POST
def tournament_fixture_result(request, pk):
    if not _is_admin(request.user):
        return redirect('/')
    result = request.POST.get('result', '')
    try:
        record_fixture_result(pk, result)
    except (DrawError, TournamentFixture.DoesNotExist) as exc:
        messages.error(request, str(exc) or 'Không tìm thấy ván đấu.')
    else:
        messages.success(request, 'Đã lưu kết quả. Bảng xếp hạng và nhánh đấu được cập nhật.')
    return redirect('/season-admin/')


def rules_markdown_download(request):
    path = Path(settings.BASE_DIR) / 'docs' / 'LUAT_XEP_BANG_VA_SO_DO_GIAI.md'
    if not path.is_file():
        return JsonResponse({'error': 'Không tìm thấy tài liệu luật giải.'}, status=404)
    from django.http import FileResponse
    return FileResponse(path.open('rb'), as_attachment=True, filename='LUAT_XEP_BANG_VA_SO_DO_GIAI.md')


# ── admin: xem source code submission ────────────────────────────────

def admin_submission_code(request, pk):
    """
    Trả source_code của một submission cho admin — JSON.
    Đã cập nhật: trả review_status thay vì status/score (đã bỏ).
    """
    if not _is_admin(request.user):
        return JsonResponse({'error': 'Không có quyền'}, status=403)
    from submissions.models import Submission
    try:
        sub = Submission.objects.select_related('submitter', 'approved_by').get(pk=pk)
    except Submission.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy'}, status=404)
    return JsonResponse({
        'id': sub.pk,
        'submitter': sub.submitter.username,
        'ai_name': sub.ai_name,
        'version': sub.version,
        'source_code': sub.source_code,
        'review_status': sub.review_status,
        'reject_reason': sub.reject_reason,
        'approved_by': sub.approved_by.username if sub.approved_by else None,
        'approved_at': sub.approved_at.isoformat() if sub.approved_at else None,
        'submitted_at': sub.submitted_at.isoformat(),
        'used_in_battle': sub.used_in_battle,
    })


# ── admin: trang duyệt code cộng đồng ────────────────────────────────

@login_required(login_url='/login/')
def admin_code_review(request):
    """
    Trang admin duyệt code AI do user nộp.
    Hiển thị danh sách, cho phép xem/approve/reject/delete ngay trên trang.
    """
    if not _is_admin(request.user):
        return redirect('/')

    from submissions.models import Submission

    # Filter theo status nếu có
    status_filter = request.GET.get('status', '')
    qs = Submission.objects.select_related('submitter', 'approved_by').order_by('-submitted_at')
    if status_filter in ('pending', 'approved', 'rejected'):
        qs = qs.filter(review_status=status_filter)

    # Thống kê nhanh
    counts = Submission.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(review_status='pending')),
        approved=Count('id', filter=Q(review_status='approved')),
        rejected=Count('id', filter=Q(review_status='rejected')),
    )

    return render(request, 'web/admin_code_review.html', {
        'user': request.user,
        'is_admin': True,
        'submissions': qs,
        'status_filter': status_filter,
        'counts': counts,
    })


# ── legacy ────────────────────────────────────────────────────────────

def ranking_view(request):
    """Trang bảng xếp hạng ELO — truyền user để template highlight hàng của mình."""
    return render(request, 'web/ranking.html', {
        'user': request.user,
        'page': 'ranking',
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })


@login_required(login_url='/login/')
@ensure_csrf_cookie
def ai_submit(request):
    """Trang nộp code AI — user upload, admin nhận."""
    from submissions.models import Submission
    my_subs = Submission.objects.filter(submitter=request.user).order_by('-submitted_at')
    return render(request, 'web/ai_judge.html', {
        'user': request.user, 'page': 'play',
        'my_subs': my_subs,
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })


@login_required(login_url='/login/')
@ensure_csrf_cookie
def competition_hub(request):
    """Season registration UI; mutations are handled by scoped competition APIs."""
    return render(request, 'web/competition.html', {
        'user': request.user, 'page': 'play',
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })


@login_required(login_url='/login/')
def ai_battle(request):
    """
    Trang battle AI vs AI.
    Truyền vào template:
      - my_subs: code đã duyệt của chính user (để chọn ở optgroup đầu)
      - community_bots: tất cả code đã duyệt (kể cả của user, để optgroup "cộng đồng")
    """
    from submissions.models import Submission
    # Code của chính user đã được duyệt
    my_subs = Submission.objects.filter(
        submitter=request.user,
        review_status='approved',
    ).order_by('ai_name', '-version')
    # Toàn bộ code đã duyệt (mọi user) — hiển thị trong optgroup cộng đồng
    community_bots = Submission.objects.filter(
        review_status='approved',
    ).select_related('submitter').order_by('submitter__username', 'ai_name')

    return render(request, 'web/ai_battle.html', {
        'user': request.user,
        'my_subs': my_subs,
        'community_bots': community_bots,
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })

def rooms_api(request):
    from django.http import JsonResponse
    from .room_manager import RoomManager, MAX_SPECTATORS
    rm = RoomManager.get_instance()
    return JsonResponse([{
        'code': r.code, 'names': list(r.names), 'status': r.status,
        'spectatorCount': len(r.spectators), 'maxSpectators': MAX_SPECTATORS,
        'turnNumber': r.state.turn_number, 'currentPlayer': r.state.current_player,
        'gameOver': r.state.game_over, 'winner': r.state.winner,
    } for r in rm.rooms.values()], safe=False)
