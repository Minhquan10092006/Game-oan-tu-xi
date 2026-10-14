"""Battlecode demo API — lưu mỗi trận vào MatchHistory."""
from __future__ import annotations
import json, tempfile
from pathlib import Path
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from .game_engine import board_presets
from .match_manager import MatchManager

MATCHES = {}
MAX_UPLOAD = 256 * 1024


def _save_history(request, result, p1_name, p2_name):
    try:
        from web.models import MatchHistory, Season
        raw = result.get('result', '')
        winner = result.get('winner') or ''
        if raw == 'win':
            res = 'p1_win' if winner == 'P1' else 'p2_win'
        elif raw == 'draw':
            res = 'draw'
        else:
            res = 'error'
        reason = result.get('reason') or {}
        player = request.user if request.user.is_authenticated else None
        season = Season.objects.filter(is_active=True).first()
        MatchHistory.objects.create(
            match_id=result['id'], player=player, season=season,
            board_preset=result.get('board_preset', 'classic_9x9'),
            result=res, winner=winner,
            total_plies=result.get('ply', 0),
            reason_code=reason.get('code', ''),
            reason_message=reason.get('message', ''),
            replay_data=json.dumps(result),
            player1_filename=p1_name, player2_filename=p2_name,
        )
    except Exception:
        pass


@require_GET
def approved_bots(request):
    """
    GET /api/matches/approved-bots/
    Trả danh sách code AI đã được admin duyệt (id, label).
    Dùng để populate dropdown trong battlecode UI.
    """
    try:
        from submissions.models import Submission
        bots = Submission.objects.filter(review_status='approved').select_related('submitter')
        return JsonResponse([{
            'id': b.id,
            'label': f'{b.ai_name} v{b.version} — by {b.submitter.username}',
            'ai_name': b.ai_name,
            'submitter': b.submitter.username,
        } for b in bots], safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_POST
def run_approved_bot_match(request):
    """
    POST /api/matches/demo-approved/
    Chạy trận giữa một file upload (P1) và một approved bot (P2).
    Body form-data:
      - player1_file: file .py
      - approved_bot_id: int — id của Submission đã approved
      - preset, max_plies, timeout (tùy chọn)
    """
    import tempfile, json
    from submissions.models import Submission

    p1 = request.FILES.get('player1_file')
    bot_id = request.POST.get('approved_bot_id')

    if not p1 or not bot_id:
        return JsonResponse({'error': 'Cần player1_file và approved_bot_id.'}, status=400)
    if Path(p1.name).suffix.lower() != '.py' or p1.size > MAX_UPLOAD:
        return JsonResponse({'error': 'File P1 phải là .py, tối đa 256 KB.'}, status=400)

    try:
        bot = Submission.objects.get(pk=int(bot_id), review_status='approved')
    except (Submission.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Bot không tồn tại hoặc chưa được duyệt.'}, status=404)

    preset = request.POST.get('preset', 'classic_9x9')
    try:
        max_plies = min(max(int(request.POST.get('max_plies', 300)), 1), 300)
        timeout = min(max(float(request.POST.get('timeout', 2)), .1), 10)
        with tempfile.TemporaryDirectory(prefix='ott-approved-') as d:
            # Lưu P1 từ upload
            p1_path = Path(d) / 'player1.py'
            p1_path.write_bytes(b''.join(p1.chunks()))
            # Lưu P2 từ DB
            p2_path = Path(d) / 'player2.py'
            p2_path.write_text(bot.source_code, encoding='utf-8')

            result = MatchManager().run(p1_path, p2_path, preset=preset,
                                        max_plies=max_plies, timeout=timeout)
    except (ValueError, OSError) as e:
        return JsonResponse({'error': str(e)}, status=400)

    MATCHES[result['id']] = result

    # Đánh dấu bot đã được dùng trong battle
    Submission.objects.filter(pk=bot.pk).update(used_in_battle=True)

    # Lưu lịch sử
    _save_history(request, result, p1.name, f'{bot.ai_name} v{bot.version} (by {bot.submitter.username})')

    return JsonResponse({
        'match_id': result['id'], 'status': result['status'],
        'ply': result['ply'], 'result': result['result'],
        'winner': result.get('winner'),
        'bot_label': f'{bot.ai_name} v{bot.version} by {bot.submitter.username}',
    }, status=201)


@require_GET
def boards(request):
    return JsonResponse({
        name: {k: v for k, v in val.items() if k != 'initial_pieces'}
        for name, val in board_presets().items()
    })


@csrf_exempt
@require_POST
def create_demo_match(request):
    p1 = request.FILES.get('player1_file')
    p2 = request.FILES.get('player2_file')
    if not p1 or not p2:
        return JsonResponse({'error': 'Cần tải lên bot Player 1 và Player 2.'}, status=400)
    if any(Path(f.name).suffix.lower() != '.py' or f.size > MAX_UPLOAD for f in (p1, p2)):
        return JsonResponse({'error': 'Chỉ chấp nhận file .py, tối đa 256 KB.'}, status=400)
    preset = request.POST.get('preset', 'classic_9x9')
    try:
        max_plies = min(max(int(request.POST.get('max_plies', 300)), 1), 300)
        timeout = min(max(float(request.POST.get('timeout', 2)), .1), 10)
        with tempfile.TemporaryDirectory(prefix='ott-') as d:
            paths = []
            for i, up in enumerate((p1, p2), 1):
                p = Path(d) / f'player{i}.py'
                p.write_bytes(b''.join(up.chunks()))
                paths.append(p)
            result = MatchManager().run(*paths, preset=preset, max_plies=max_plies, timeout=timeout)
    except (ValueError, OSError) as e:
        return JsonResponse({'error': str(e)}, status=400)
    MATCHES[result['id']] = result
    _save_history(request, result, p1.name, p2.name)
    return JsonResponse({'match_id': result['id'], 'status': result['status'],
                         'ply': result['ply'], 'result': result['result'],
                         'winner': result.get('winner')}, status=201)


@require_GET
def demo_match_detail(request, match_id):
    result = MATCHES.get(match_id)
    if not result:
        try:
            from web.models import MatchHistory
            rec = MatchHistory.objects.filter(match_id=match_id).first()
            if rec:
                result = rec.get_replay()
        except Exception:
            pass
    if not result:
        return JsonResponse({'error': 'Không tìm thấy trận.'}, status=404)
    return JsonResponse(result)


@require_GET
def demo_match_state(request, match_id):
    result = MATCHES.get(match_id)
    if not result:
        try:
            from web.models import MatchHistory
            rec = MatchHistory.objects.filter(match_id=match_id).first()
            if rec:
                result = rec.get_replay()
        except Exception:
            pass
    if not result:
        return JsonResponse({'error': 'Không tìm thấy trận.'}, status=404)
    return JsonResponse(result['state'])
