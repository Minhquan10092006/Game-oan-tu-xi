from __future__ import annotations
import json, uuid
import logging
from pathlib import Path
from django.conf import settings
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
    from .tournament_ops import can_operate
    return can_operate(user)

def _ensure_profile(user):
    UserProfile.objects.get_or_create(user=user)


# ── auth wall ────────────────────────────────────────────────────────

def index(request):
    """Public competition landing page; authentication is a separate destination."""
    if request.method == 'POST':
        return account(request)  # Compatibility with existing sign-in forms.
    if _is_admin(request.user):
        return redirect('/tournament/')
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
    if _is_admin(request.user):
        return redirect('/tournament/')
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
                if _is_admin(user) and next_url.split('?')[0] in ('/', '/play/', '/ai/', '/competition/', '/register/'):
                    return redirect('/tournament/')
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
    matches = MatchHistory.objects.all() if _is_admin(request.user) else MatchHistory.objects.filter(player=request.user)
    matches = matches.order_by('-played_at')
    return render(request, 'web/history.html', {
        'user': request.user, 'matches': matches, 'page': 'play',
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })


@login_required(login_url='/login/')
def match_detail(request, match_id):
    matches = MatchHistory.objects.all() if _is_admin(request.user) else MatchHistory.objects.filter(player=request.user)
    match = get_object_or_404(matches, match_id=match_id)
    return render(request, 'web/match_detail.html', {
        'user': request.user, 'match': match,
        'replay_json': json.dumps(match.get_replay()) if match.get_replay() else 'null',
        'is_admin': _is_admin(request.user),
    })


# ── mùa giải (admin) ─────────────────────────────────────────────────





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
    if s.audit_events.exists() or s.judging_jobs.exists():
        messages.error(request, 'Mùa giải có nhật ký hoặc tác vụ chấm phải được giữ để đối chiếu; không thể xóa.')
        return redirect('/tournament/')
    name = s.name; s.delete()
    messages.success(request, f'Đã xoá "{name}".')
    return redirect('/season-admin/')












@login_required(login_url='/login/')
@require_POST
def tournament_fixture_result(request, pk):
    if not _is_admin(request.user):
        return redirect('/')
    fixture = get_object_or_404(TournamentFixture.objects.select_related('tournament_round__season'), pk=pk)
    if fixture.tournament_round.season.judge_image:
        messages.error(request, 'Trận thuộc bộ chấm tự động; xử lý tại bàn điều hành để tránh xung đột kết quả.')
        return redirect('/tournament/')
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
    qs = Submission.objects.select_related('submitter', 'approved_by', 'competition_entry__season').defer('source_code').order_by('-submitted_at')
    if status_filter in ('pending', 'approved', 'rejected'):
        qs = qs.filter(review_status=status_filter)
    from django.core.paginator import Paginator
    submission_page = Paginator(qs, 50).get_page(request.GET.get('page', 1))

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
        'submissions': submission_page,
        'page': 'submissions-admin',
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
    if _is_admin(request.user):
        return redirect('/admin/code-review/')
    """Trang nộp code AI — user upload, admin nhận."""
    from submissions.models import Submission
    my_subs = Submission.objects.filter(submitter=request.user).order_by('-submitted_at')
    from .models import CompetitionEntry
    entries = list(CompetitionEntry.objects.filter(user=request.user, status='registered',
        season__is_active=True, season__phase__in=['registration', 'submission']).filter(
        Q(season__submission_deadline__isnull=True) | Q(season__submission_deadline__gte=timezone.now())
    ).select_related('season'))
    requested_entry = request.GET.get('entry', '')
    selected_entry = next((e.pk for e in entries if str(e.pk) == requested_entry), None)
    if selected_entry is None and len(entries) == 1:
        selected_entry = entries[0].pk
    if not entries:
        active = Season.objects.filter(is_active=True).order_by('-created_at').first()
        return render(request, 'web/submission_closed.html', {
            'page': 'play', 'user': request.user, 'season': active,
            'is_guest': request.session.get('is_guest', False), 'is_admin': _is_admin(request.user),
        })
    return render(request, 'web/ai_judge.html', {
        'user': request.user, 'page': 'play',
        'my_subs': my_subs,
        'submission_entries': entries, 'selected_submission_entry': selected_entry,
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })


@login_required(login_url='/login/')
@ensure_csrf_cookie
def competition_hub(request):
    """Season registration UI; mutations are handled by scoped competition APIs."""
    if _is_admin(request.user):
        return redirect('/tournament/')
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
