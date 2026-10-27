"""
matches/views.py
----------------
REST API cho trận đấu và nước đi AI.

POST /api/matches/                — tạo trận đấu
GET  /api/matches/{id}/           — chi tiết trận đấu
POST /api/matches/{id}/ai-move/   — yêu cầu AI đề xuất nước đi
"""
import json
import logging
import asyncio
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.utils import timezone
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Match, MatchMove
from .serializers import (
    MatchCreateSerializer,
    MatchDetailSerializer,
    AIMoveRequestSerializer,
)
from .engine import GameState, build_ai_input, parse_ai_output, validate_ai_move
from judge.client import get_client, Judge0Error, Judge0Unavailable
from submissions.models import Submission

logger = logging.getLogger(__name__)

# Global thread pool for running matches in background
_match_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='match_worker')


class MatchListCreateView(generics.ListCreateAPIView):
    """
    POST /api/matches/ → tạo trận đấu mới
    GET  /api/matches/ → danh sách trận đấu của user
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MatchCreateSerializer
        return MatchDetailSerializer

    def get_queryset(self):
        return Match.objects.filter(player1=self.request.user)

    def perform_create(self, serializer):
        serializer.save(player1=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        detail = MatchDetailSerializer(serializer.instance, context={'request': request})
        return Response(detail.data, status=status.HTTP_201_CREATED)


class MatchDetailView(generics.RetrieveAPIView):
    """
    GET /api/matches/{id}/ → chi tiết trận đấu
    """
    serializer_class = MatchDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Match.objects.filter(player1=self.request.user)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def ai_move_view(request, pk: int):
    """
    POST /api/matches/{id}/ai-move/
    Body: {"player": 1, "submission_id": 42}

    Yêu cầu AI submission đề xuất nước đi cho trạng thái hiện tại.
    Nếu không cung cấp submission_id, dùng AI đã gán trong match.

    Quy trình:
    1. Lấy trạng thái match hiện tại.
    2. Build AI input JSON.
    3. Gửi lên Judge0 qua submission code.
    4. Nhận output → parse → validate bằng game engine.
    5. Nếu hợp lệ → execute move → lưu → trả kết quả.
    """
    try:
        match = Match.objects.get(pk=pk, player1=request.user)
    except Match.DoesNotExist:
        return Response(
            {'error': True, 'message': 'Trận đấu không tồn tại.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if match.status == 'finished':
        return Response(
            {'error': True, 'message': 'Trận đấu đã kết thúc.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    req_serializer = AIMoveRequestSerializer(data=request.data)
    req_serializer.is_valid(raise_exception=True)
    player = req_serializer.validated_data['player']
    submission_id = req_serializer.validated_data.get('submission_id')

    # Tái tạo trạng thái game
    state = GameState.from_dict(match.board_state)

    if state.game_over:
        return Response(
            {'error': True, 'message': 'Ván đấu đã kết thúc.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if state.current_player != player:
        return Response(
            {'error': True, 'message': f'Chưa đến lượt Player {player}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Tìm submission AI
    submission = _resolve_submission(match, player, submission_id)
    if submission is None:
        return Response(
            {'error': True, 'message': 'Không tìm thấy bài nộp AI.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Build input và gọi Judge0
    ai_input = build_ai_input(state)
    stdin = json.dumps(ai_input)

    try:
        client = get_client()
        lang_id = client.get_python3_language_id()
        result = client.submit_and_wait(submission.source_code, stdin, lang_id)
    except Judge0Unavailable as e:
        logger.warning('Judge0 unavailable for match %s: %s', pk, e)
        return Response(
            {'error': True, 'message': f'Judge0 không khả dụng: {e}'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Judge0Error as e:
        logger.error('Judge0 error for match %s: %s', pk, e)
        return Response(
            {'error': True, 'message': 'Lỗi hệ thống chấm bài.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    raw_output = result.stdout

    # Parse output
    move = parse_ai_output(raw_output)
    if move is None:
        return Response(
            {
                'error': True,
                'message': 'AI không trả về nước đi hợp lệ (parse error).',
                'ai_stdout': raw_output[:200],
                'ai_stderr': result.stderr[:200],
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Validate bằng game engine — chỉ engine mới có quyền xác nhận
    validation = validate_ai_move(state, move)
    if not validation['valid']:
        return Response(
            {
                'error': True,
                'message': f'Nước đi không hợp lệ: {validation["reason"]}',
                'move': move,
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # Execute move
    move_record = state.execute_move(
        move['from_row'], move['from_col'],
        move['to_row'], move['to_col'],
    )

    # Lưu move vào DB
    MatchMove.objects.create(
        match=match,
        player=player,
        turn_number=move_record['turn_number'],
        from_row=move['from_row'],
        from_col=move['from_col'],
        to_row=move['to_row'],
        to_col=move['to_col'],
        piece_type=move_record['piece'].type,
        is_capture=move_record['is_capture'],
        captured_type=move_record['captured'].type if move_record.get('captured') else '',
        ai_raw_output=raw_output[:1000],
    )

    # Cập nhật match state
    new_state = state.to_dict()
    match.board_state = new_state
    match.current_player = state.current_player
    match.turn_number = state.turn_number

    if state.game_over:
        match.status = 'finished'
        match.winner = state.winner
        match.win_reason = state.win_reason
        match.finished_at = timezone.now()
        # Cập nhật ELO nếu cả hai bên là người thật (không phải AI-only)
        _try_update_elo(match, state.winner)

    match.save()

    return Response({
        'move': move,
        'move_record': {
            'player': player,
            'turn_number': move_record['turn_number'],
            'is_capture': move_record['is_capture'],
            'captured_type': (
                move_record['captured'].type if move_record.get('captured') else None
            ),
        },
        'state': new_state,
        'game_over': state.game_over,
        'winner': state.winner,
        'win_reason': state.win_reason,
    })


def _resolve_submission(match: Match, player: int,
                         submission_id=None) -> Submission | None:
    """Tìm submission AI cho player."""
    # Dùng review_status='approved' thay status='completed' (đã bỏ migration 0003)
    if submission_id:
        try:
            return Submission.objects.get(pk=submission_id, review_status='approved')
        except Submission.DoesNotExist:
            return None

    # Dùng AI gán trong match
    ai = match.ai1 if player == 1 else match.ai2
    return ai


def _try_update_elo(match: Match, winner_player: int | str):
    """Cập nhật ELO cho người chơi sau trận đấu."""
    try:
        from web.models import update_elo_after_match, update_user_elo_solo, UserProfile
        p1 = match.player1
        p2 = match.player2
        if not p1 and not p2:
            return

        # Chuẩn hóa winner: 1, 2, 'P1', 'P2', hoặc None/0
        if winner_player in (1, 'P1', '1'):
            winner_int = 1
        elif winner_player in (2, 'P2', '2'):
            winner_int = 2
        else:
            winner_int = None

        if p1 and p2 and p1 != p2:
            if winner_int == 1:
                update_elo_after_match(p1, p2)
            elif winner_int == 2:
                update_elo_after_match(p2, p1)
            else:
                p1_prof, _ = UserProfile.objects.get_or_create(user=p1)
                p2_prof, _ = UserProfile.objects.get_or_create(user=p2)
                p1_prof.draws += 1
                p1_prof.save(update_fields=['draws', 'updated_at'])
                p2_prof.draws += 1
                p2_prof.save(update_fields=['draws', 'updated_at'])
        elif p1 and (not p2 or p1 == p2):
            won = True if winner_int == 1 else (False if winner_int == 2 else None)
            update_user_elo_solo(p1, won)
        elif p2 and not p1:
            won = True if winner_int == 2 else (False if winner_int == 1 else None)
            update_user_elo_solo(p2, won)
    except Exception as e:
        logger.warning('ELO update failed for match %s: %s', match.pk, e)



@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def ai_battle_start_view(request):
    """
    POST /api/matches/ai-battle/start/
    Body: {"ai1_id": 1, "ai2_id": 2}

    Tạo trận AI vs AI và chạy trong background.
    Trả về match_id ngay lập tức (status=queued).
    Client dùng GET /api/matches/{id}/battle/ hoặc WebSocket để theo dõi.
    """
    ai1_id = request.data.get('ai1_id')
    ai2_id = request.data.get('ai2_id')

    if not ai1_id or not ai2_id:
        return Response(
            {'error': True, 'message': 'Cần cung cấp ai1_id và ai2_id.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        ai1 = Submission.objects.get(pk=ai1_id, review_status='approved')
        ai2 = Submission.objects.get(pk=ai2_id, review_status='approved')
    except Submission.DoesNotExist:
        return Response(
            {'error': True, 'message': 'Một hoặc cả hai bài nộp không tồn tại hoặc chưa được admin duyệt.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from matches.engine import GameState
    gs = GameState()
    match = Match.objects.create(
        player1=ai1.submitter,
        player2=ai2.submitter,
        player1_name=ai1.ai_name,
        player2_name=ai2.ai_name,
        ai1=ai1,
        ai2=ai2,
        board_state=gs.to_dict(),
        status='queued',
        max_turns=200,
    )

    # Ghi source code ra file tạm để BotRunner dùng
    p1_source = _write_bot_to_temp(ai1.source_code, f'p1_{ai1.id}')
    p2_source = _write_bot_to_temp(ai2.source_code, f'p2_{ai2.id}')

    # Chạy match trong background thread pool
    loop = asyncio.get_event_loop()
    future = loop.run_in_executor(
        _match_executor,
        _run_match_background,
        match.id,
        p1_source,
        p2_source,
    )
    future.add_done_callback(lambda f: f.exception() and logger.error(f"Match {match.id} failed: {f.exception()}"))

    return Response({
        'match_id': match.id,
        'status': 'queued',
        'message': 'Trận đấu đang chờ thực thi. Dùng GET /api/matches/{id}/battle/ để theo dõi.',
    }, status=status.HTTP_202_ACCEPTED)


def _write_bot_to_temp(source_code: str, prefix: str) -> str:
    """Ghi source code ra file tạm, trả về path. File sẽ bị xóa sau khi match xong."""
    fd, path = tempfile.mkstemp(suffix='.py', prefix=prefix + '_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(source_code)
    except Exception:
        os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def _run_match_background(match_id: int, p1_source: str, p2_source: str):
    """
    Chạy trong thread pool. Tự setup Django, chạy match, lưu kết quả, push WebSocket.
    """
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

    from matches.match_manager import MatchManager
    from matches.models import Match
    from channels.layers import get_channel_layer

    try:
        match = Match.objects.get(id=match_id)
        match.status = 'playing'
        match.save(update_fields=['status'])

        manager = MatchManager()
        result = manager.run(
            Path(p1_source),
            Path(p2_source),
            preset='classic_9x9',
            max_plies=300,
            timeout=5.0,
            match_id=f'match-{match_id}',
        )

        # Cập nhật kết quả
        match.status = 'finished'
        match.winner = result['winner']
        match.win_reason = result['reason']['message'] if result.get('reason') else ''
        match.replay_data = result
        match.finished_at = timezone.now()
        _try_update_elo(match, match.winner)
        match.save(update_fields=['status', 'winner', 'win_reason', 'replay_data', 'finished_at'])

        # Push WebSocket event
        channel_layer = get_channel_layer()
        if channel_layer:
            asyncio.run(channel_layer.group_send(
                f'match_{match_id}',
                {'type': 'match_finished', 'data': result}
            ))

    except Exception as e:
        logger.exception(f"Match {match_id} error: {e}")
        try:
            match = Match.objects.get(id=match_id)
            match.status = 'error'
            match.win_reason = f'Lỗi hệ thống: {str(e)[:200]}'
            match.save(update_fields=['status', 'win_reason'])
        except Exception:
            pass
    finally:
        # Cleanup temp files
        for path in (p1_source, p2_source):
            try:
                os.unlink(path)
            except OSError:
                pass


@api_view(['GET'])
@permission_classes([AllowAny])
def ai_battle_status_view(request, pk: int):
    """GET /api/matches/<pk>/battle/ — Trả trạng thái + toàn bộ nước đi của trận."""
    try:
        match = Match.objects.get(pk=pk)
    except Match.DoesNotExist:
        return Response({'error': True, 'message': 'Không tìm thấy trận.'}, status=404)

    moves = list(MatchMove.objects.filter(match=match).order_by('id').values(
        'player', 'turn_number', 'from_row', 'from_col',
        'to_row', 'to_col', 'piece_type', 'is_capture', 'captured_type',
    ))

    ai1 = match.ai1
    ai2 = match.ai2
    return Response({
        'match_id': match.pk,
        'status': match.status,
        'winner': match.winner,
        'win_reason': match.win_reason,
        'board_state': match.board_state,
        'total_moves': len(moves),
        'moves': moves,
        'ai1': {'id': ai1.pk, 'name': ai1.ai_name, 'elo': ai1.elo} if ai1 else None,
        'ai2': {'id': ai2.pk, 'name': ai2.ai_name, 'elo': ai2.elo} if ai2 else None,
    })

