from __future__ import annotations
import json, uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from .models import UserProfile, Season, MatchHistory


# ── helpers ──────────────────────────────────────────────────────────

def _is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

def _ensure_profile(user):
    UserProfile.objects.get_or_create(user=user)


# ── auth wall ────────────────────────────────────────────────────────

def index(request):
    """Nếu đã đăng nhập → trang chủ; nếu chưa → auth overlay ngay trên index."""
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
        'auth_mode': 'login',
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'login':
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            user = authenticate(request, username=username, password=password)
            if user:
                login(request, user); _ensure_profile(user)
                return redirect('/')
            context['auth_error'] = 'Tên đăng nhập hoặc mật khẩu không đúng.'
            context['auth_mode'] = 'login'

        elif action == 'register':
            context['auth_mode'] = 'register'
            uname = request.POST.get('reg_username', '').strip()
            pw1   = request.POST.get('reg_password1', '')
            pw2   = request.POST.get('reg_password2', '')
            errs  = {}
            if not uname or len(uname) < 3:
                errs['username'] = 'Tối thiểu 3 ký tự.'
            elif User.objects.filter(username=uname).exists():
                errs['username'] = 'Tên đăng nhập đã tồn tại.'
            if len(pw1) < 6:
                errs['password1'] = 'Tối thiểu 6 ký tự.'
            elif pw1 != pw2:
                errs['password2'] = 'Hai mật khẩu không khớp.'
            if not errs:
                user = User.objects.create_user(username=uname, password=pw1)
                _ensure_profile(user); login(request, user)
                return redirect('/')
            context['reg_errors'] = errs

        elif action == 'guest':
            gname = f'guest_{uuid.uuid4().hex[:8]}'
            user  = User.objects.create_user(username=gname, password=uuid.uuid4().hex)
            _ensure_profile(user); login(request, user)
            request.session['is_guest'] = True
            return redirect('/')

    return render(request, 'web/index.html', context)


# ── logout ───────────────────────────────────────────────────────────

def logout_view(request):
    if request.session.get('is_guest') and request.user.is_authenticated:
        try: request.user.delete()
        except Exception: pass
    logout(request)
    return redirect('/')


# ── battlecode ───────────────────────────────────────────────────────

@login_required(login_url='/')
def battlecode_demo(request):
    active_season = Season.objects.filter(is_active=True).first()
    return render(request, 'web/battlecode_demo.html', {
        'user': request.user,
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
        'active_season': active_season,
    })


# ── lịch sử ──────────────────────────────────────────────────────────

@login_required(login_url='/')
def match_history(request):
    matches = MatchHistory.objects.filter(player=request.user).order_by('-played_at')
    return render(request, 'web/history.html', {
        'user': request.user, 'matches': matches,
        'is_guest': request.session.get('is_guest', False),
        'is_admin': _is_admin(request.user),
    })


@login_required(login_url='/')
def match_detail(request, match_id):
    match = get_object_or_404(MatchHistory, match_id=match_id, player=request.user)
    return render(request, 'web/match_detail.html', {
        'user': request.user, 'match': match,
        'replay_json': json.dumps(match.get_replay()) if match.get_replay() else 'null',
        'is_admin': _is_admin(request.user),
    })


# ── mùa giải (admin) ─────────────────────────────────────────────────

@login_required(login_url='/')
def season_admin(request):
    if not _is_admin(request.user):
        return redirect('/')
    from submissions.models import Submission
    seasons = Season.objects.all()
    all_submissions = Submission.objects.select_related('submitter').order_by('-submitted_at')
    return render(request, 'web/season_admin.html', {
        'user': request.user, 'seasons': seasons,
        'is_admin': True,
        'total_matches': MatchHistory.objects.count(),
        'total_users': User.objects.filter(is_staff=False).count(),
        'total_submissions': all_submissions.count(),
        'recent_matches': MatchHistory.objects.select_related('player','season').order_by('-played_at')[:20],
        'all_submissions': all_submissions[:50],
    })


@login_required(login_url='/')
@require_POST
def season_create(request):
    if not _is_admin(request.user): return redirect('/')
    name = request.POST.get('name','').strip()
    if not name:
        messages.error(request, 'Tên mùa giải không được trống.')
        return redirect('/season-admin/')
    Season.objects.create(
        name=name,
        description=request.POST.get('description','').strip(),
        start_date=request.POST.get('start_date') or timezone.now().date(),
        is_active=True, created_by=request.user,
    )
    messages.success(request, f'Đã tạo mùa giải "{name}".')
    return redirect('/season-admin/')


@login_required(login_url='/')
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


@login_required(login_url='/')
@require_POST
def season_delete(request, pk):
    if not _is_admin(request.user): return redirect('/')
    s = get_object_or_404(Season, pk=pk)
    name = s.name; s.delete()
    messages.success(request, f'Đã xoá "{name}".')
    return redirect('/season-admin/')


# ── admin: xem source code submission ────────────────────────────────

def admin_submission_code(request, pk):
    """Trả source_code của submission cho admin — JSON."""
    if not _is_admin(request.user):
        return JsonResponse({'error': 'Không có quyền'}, status=403)
    from submissions.models import Submission
    try:
        sub = Submission.objects.get(pk=pk)
    except Submission.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy'}, status=404)
    return JsonResponse({
        'id': sub.pk,
        'submitter': sub.submitter.username,
        'ai_name': sub.ai_name,
        'version': sub.version,
        'source_code': sub.source_code,
        'status': sub.status,
        'score': sub.score,
        'submitted_at': sub.submitted_at.isoformat(),
    })


# ── legacy ────────────────────────────────────────────────────────────

def ranking_view(request):
    return render(request, 'web/ranking.html')


@login_required(login_url='/')
def ai_submit(request):
    """Trang nộp code AI — user upload, admin nhận."""
    from submissions.models import Submission
    my_subs = Submission.objects.filter(submitter=request.user).order_by('-submitted_at')
    return render(request, 'web/ai_judge.html', {
        'user': request.user,
        'my_subs': my_subs,
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
