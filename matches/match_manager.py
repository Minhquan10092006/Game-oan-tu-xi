from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import tempfile
import uuid
from .bot_runner import BotError, BotRunner, RunnerUnavailable
from .game_engine import GameState, RULES_VERSION, board_presets


class MatchManager:
    """Authoritative engine. Bot faults forfeit; infrastructure faults do not score."""
    def __init__(self, runner_factory=BotRunner):
        self.runner_factory = runner_factory

    def run(self, p1_source, p2_source, preset='classic_9x9', max_plies=300,
            timeout=5.0, match_id=None):
        if preset not in board_presets():
            raise ValueError('Preset không tồn tại')
        if type(max_plies) is not int or not 1 <= max_plies <= 300:
            raise ValueError('max_plies phải từ 1 đến 300')
        match_id = match_id or f'match-{uuid.uuid4().hex}'
        state = GameState(board_presets()[preset], max_plies)
        events = [{'type': 'started', 'state_after': state.snapshot()}]
        userdata, runs, runners, errors = {'P1': None, 'P2': None}, [], {}, {}
        with tempfile.TemporaryDirectory(prefix='ott-battle-') as root:
            try:
                for player, source in (('P1', p1_source), ('P2', p2_source)):
                    try:
                        runners[player] = self.runner_factory(source, Path(root) / player, timeout)
                    except BotError as exc:
                        errors[player] = exc
                if errors:
                    if len(errors) == 2:
                        state.finish(None, 'error', 'bot_initialization_failed', 'Cả hai bot không khởi tạo được; BTC kiểm tra')
                    else:
                        player, exc = next(iter(errors.items()))
                        state.finish('P2' if player == 'P1' else 'P1', 'forfeit', exc.code, f'{player}: {exc.message}')
                while not state.finished:
                    if state.check_turn_start():
                        break
                    player = state.current_player
                    try:
                        output, run = runners[player].run_turn(deepcopy(state.bot_input(match_id, userdata[player])))
                        runs.append({'player': player, **run})
                        event = state.apply_move(output['move'])
                        userdata[player] = output.get('userdata')
                    except BotError as exc:
                        state.finish('P2' if player == 'P1' else 'P1', 'forfeit', exc.code, f'{player}: {exc.message}')
                        runs.append({'player': player, 'stderr': exc.stderr, 'error': exc.code})
                        break
                    except ValueError as exc:
                        state.finish('P2' if player == 'P1' else 'P1', 'forfeit', 'illegal_move', f'{player}: {exc}')
                        break
                    events.append(event)
            except RunnerUnavailable as exc:
                runs.append({'error': 'infrastructure_error', 'message': str(exc)})
                state.finish(None, 'error', 'infrastructure_error', 'Lỗi máy chấm; không tính điểm, cần chạy lại')
        events.append({'type': 'finished', 'winner': state.winner, 'result': state.result,
                       'reason': state.reason, 'final_state': state.snapshot()})
        return {'id': match_id, 'rules_version': RULES_VERSION, 'status': state.status,
                'board_preset': preset, 'ply': state.ply, 'winner': state.winner,
                'result': state.result, 'reason': state.reason, 'events': events,
                'state': state.snapshot(), 'bot_runs': runs}
