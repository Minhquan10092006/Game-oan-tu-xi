"""
matches/ai_battle.py
--------------------
Logic chạy trận đấu AI vs AI đầy đủ một ván.

Quy trình:
1. Tạo GameState mới
2. Luân phiên gọi Judge0 để lấy nước đi của từng AI
3. Validate bằng game engine Python
4. Lưu từng nước đi vào MatchMove
5. Cập nhật ELO sau khi ván kết thúc

Không có frontend realtime ở đây — chạy synchronous.
Trang /ai-battle/ poll API để cập nhật trạng thái.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from django.utils import timezone

from matches.engine import GameState, build_ai_input, parse_ai_output, validate_ai_move
from matches.models import Match, MatchMove
from submissions.models import Submission
from judge.client import get_client, Judge0Error, Judge0Unavailable
# calculate_elo đã bị bỏ (không còn ELO trên Submission)

logger = logging.getLogger(__name__)

MAX_TURNS = 200


def run_ai_battle(match: Match) -> Match:
    """
    Chạy toàn bộ ván đấu AI vs AI đến khi kết thúc hoặc hết lượt.
    Cập nhật match.board_state, status, winner, và ELO sau mỗi lượt.
    Trả về match đã cập nhật.
    """
    if match.status == 'finished':
        return match

    client = get_client()

    try:
        lang_id = client.get_python3_language_id()
    except Judge0Error as e:
        match.status = 'error'
        match.win_reason = f'Không lấy được language ID: {e}'
        match.save(update_fields=['status', 'win_reason'])
        return match

    state = GameState.from_dict(match.board_state)
    match.status = 'playing'
    match.save(update_fields=['status'])

    turn_count = 0

    while not state.game_over and turn_count < MAX_TURNS:
        player = state.current_player
        submission: Optional[Submission] = match.ai1 if player == 1 else match.ai2

        if submission is None:
            # Không có AI cho player này → kết thúc bất thường
            state.game_over = True
            state.winner = 2 if player == 1 else 1
            state.win_reason = f'P{player} không có AI — thua mặc định'
            break

        ai_input = build_ai_input(state)
        stdin = json.dumps(ai_input)

        try:
            result = client.submit_and_wait(submission.source_code, stdin, lang_id)
        except (Judge0Unavailable, Judge0Error) as e:
            logger.warning('AI Battle Judge0 error turn %d: %s', turn_count, e)
            match.status = 'error'
            match.winner = None
            match.win_reason = 'Lỗi hạ tầng Judge0; chưa tính điểm, cần BTC xử lý.'
            match.save(update_fields=['status', 'winner', 'win_reason'])
            return match

        move = parse_ai_output(result.stdout)
        if move is None:
            state.game_over = True
            state.winner = 2 if player == 1 else 1
            state.win_reason = f'P{player} AI trả output không hợp lệ'
            break

        validation = validate_ai_move(state, move)
        if not validation['valid']:
            state.game_over = True
            state.winner = 2 if player == 1 else 1
            state.win_reason = f'P{player} AI đi nước không hợp lệ: {validation["reason"]}'
            break

        move_record = state.execute_move(
            move['from_row'], move['from_col'],
            move['to_row'],   move['to_col'],
        )

        # Lưu nước đi
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
            captured_type=(move_record['captured'].type
                           if move_record.get('captured') else ''),
            ai_raw_output=result.stdout[:500],
        )

        # Cập nhật trạng thái match sau mỗi nước
        match.board_state = state.to_dict()
        match.current_player = state.current_player
        match.turn_number = state.turn_number
        match.save(update_fields=['board_state', 'current_player', 'turn_number'])

        turn_count += 1

    # Ván kết thúc
    if not state.game_over and turn_count >= MAX_TURNS:
        state.game_over = True
        state.winner = None
        state.win_reason = f'Hoà — vượt {MAX_TURNS} lượt'

    match.board_state = state.to_dict()
    match.status = 'finished'
    match.winner = state.winner
    match.win_reason = state.win_reason
    match.finished_at = timezone.now()
    match.save(update_fields=[
        'board_state', 'status', 'winner', 'win_reason', 'finished_at',
    ])

    # Cập nhật ELO cho AI submissions
    _update_ai_elo(match)

    return match


def _update_ai_elo(match: Match):
    """
    ELO/wins/losses đã bị bỏ khỏi Submission model (migration 0003).
    Chỉ đánh dấu used_in_battle cho cả hai AI submission.
    """
    ai1: Optional[Submission] = match.ai1
    ai2: Optional[Submission] = match.ai2
    for sub in (ai1, ai2):
        if sub and not sub.used_in_battle:
            Submission.objects.filter(pk=sub.pk).update(used_in_battle=True)
