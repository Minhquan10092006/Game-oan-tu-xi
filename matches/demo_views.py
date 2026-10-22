"""Public demo: trusted sample strategies only; uploaded Python runs offline."""
import json
import logging
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from .game_engine import board_presets
from .match_manager import MatchManager
from .sample_bots import SampleBotRunner

logger = logging.getLogger(__name__)


@require_GET
def boards(request):
    return JsonResponse({name: {k: v for k, v in val.items() if k != 'initial_pieces'}
                         for name, val in board_presets().items()})


@require_POST
def create_demo_match(request):
    return JsonResponse({'error': 'Demo không chạy file tải lên trên web. Hãy nộp bài tại trang Nộp AI; BTC chạy trên máy chấm riêng. Bạn có thể xem trận hai bot mẫu.'}, status=503)


@require_POST
def run_approved_bot_match(request):
    return create_demo_match(request)


@require_POST
def create_sample_match(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Cần đăng nhập để lưu trận demo.'}, status=401)
    result = MatchManager(SampleBotRunner).run('aggressive', 'defensive')
    from web.models import MatchHistory
    outcome = 'draw' if result['result'] == 'draw' else ('p1_win' if result['winner'] == 'P1' else 'p2_win')
    try:
        MatchHistory.objects.create(
            match_id=result['id'], player=request.user, season=None,
            board_preset='classic_9x9', result=outcome, winner=result['winner'] or '',
            total_plies=result['ply'], reason_code=result['reason']['code'],
            reason_message=result['reason']['message'], replay_data=json.dumps(result),
            player1_filename='Bot mẫu tiến công', player2_filename='Bot mẫu ưu tiên bắt quân',
        )
    except DatabaseError:
        logger.exception('Cannot persist demo replay %s', result['id'])
        return JsonResponse({'error': 'Chưa lưu được trận; vui lòng thử lại sau.'}, status=503)
    return JsonResponse({'match_id': result['id'], 'status': result['status'],
                         'result': result['result'], 'winner': result['winner']}, status=201)


@require_GET
def approved_bots(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Cần đăng nhập.'}, status=401)
    from submissions.models import Submission
    bots = Submission.objects.filter(review_status='approved').select_related('submitter')
    return JsonResponse([{'id': b.id, 'label': f'{b.ai_name} v{b.version} — {b.submitter.username}',
                          'ai_name': b.ai_name, 'submitter': b.submitter.username} for b in bots], safe=False)


def _get_replay(request, match_id):
    if not request.user.is_authenticated:
        return None
    from web.models import MatchHistory
    records = MatchHistory.objects.filter(match_id=match_id)
    if not (request.user.is_staff or request.user.is_superuser):
        records = records.filter(player=request.user)
    record = records.first()
    return record.get_replay() if record else None


@require_GET
def demo_match_detail(request, match_id):
    result = _get_replay(request, match_id)
    return JsonResponse(result) if result else JsonResponse({'error': 'Không tìm thấy trận.'}, status=404)


@require_GET
def demo_match_state(request, match_id):
    result = _get_replay(request, match_id)
    return JsonResponse(result['state']) if result else JsonResponse({'error': 'Không tìm thấy trận.'}, status=404)
