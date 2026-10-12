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
from web.models import calculate_elo

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
            state.game_over = True
            state.winner = 2 if player == 1 else 1
            state.win_reason = f'P{player} AI lỗi Judge0 — thua mặc định'
            break

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
    """Cập nhật ELO cho 2 AI submission sau trận."""
    ai1: Optional[Submission] = match.ai1
    ai2: Optional[Submission] = match.ai2
    if not ai1 or not ai2:
        return

    winner = match.winner
    if winner == 1:
        new_w, new_l = calculate_elo(ai1.elo, ai2.elo)
        ai1.elo, ai1.ai_wins   = new_w, ai1.ai_wins + 1
        ai2.elo, ai2.ai_losses = new_l, ai2.ai_losses + 1
    elif winner == 2:
        new_w, new_l = calculate_elo(ai2.elo, ai1.elo)
        ai2.elo, ai2.ai_wins   = new_w, ai2.ai_wins + 1
        ai1.elo, ai1.ai_losses = new_l, ai1.ai_losses + 1
    # Hoà: không đổi ELO

    ai1.save(update_fields=['elo', 'ai_wins', 'ai_losses'])
    ai2.save(update_fields=['elo', 'ai_wins', 'ai_losses'])
