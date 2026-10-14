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
