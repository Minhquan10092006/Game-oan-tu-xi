"""
judge/grader.py
---------------
Bộ chấm bài AI theo 6 nhóm kiểm tra.

Django (không phải Judge0) là bên quyết định điểm cuối cùng.
Judge0 chỉ thực thi code và trả stdout/stderr/status.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from matches.engine import GameState, build_ai_input, parse_ai_output, validate_ai_move
from judge.client import Judge0Client, Judge0Error, Judge0Unavailable, Judge0Result

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Test cases cho bộ chấm                                             #
# ------------------------------------------------------------------ #

def _make_test_states() -> list[dict]:
    """
    Tạo danh sách test cases: mỗi item là một trạng thái game.
    Bao gồm: trạng thái ban đầu, giữa ván, gần hết nước đi.
    """
    # Test 1: Trạng thái ban đầu, lượt P1
    state1 = GameState()

    # Test 2: Sau vài nước đi
    state2 = GameState()
    state2.execute_move(0, 1, 1, 1)  # P1 Rock → (1,1), ăn Scissors
    state2.execute_move(8, 7, 7, 7)  # P2 Paper → (7,7)

    # Test 3: P2's turn
    state3 = GameState()
    state3.execute_move(2, 0, 3, 0)  # P1 di chuyển

    return [
        {'id': 1, 'description': 'Trạng thái ban đầu, lượt P1', 'state': state1},
        {'id': 2, 'description': 'Sau 2 nước đi', 'state': state2},
        {'id': 3, 'description': 'Lượt P2', 'state': state3},
    ]


# ------------------------------------------------------------------ #
# Dataclasses kết quả                                                 #
# ------------------------------------------------------------------ #

@dataclass
class GroupResult:
    group: str
    passed: bool
    score: float
    max_score: float
    message: str
    details: Optional[dict] = None


@dataclass
class GradingReport:
    """Báo cáo chấm toàn bộ."""
    submission_id: int
    total_score: float
    max_score: float
    groups: list[GroupResult] = field(default_factory=list)
    error: str = ''

    def to_dict(self) -> dict:
        return {
            'submission_id': self.submission_id,
            'total_score': round(self.total_score, 2),
            'max_score': self.max_score,
            'percentage': round(100 * self.total_score / self.max_score, 1) if self.max_score else 0,
            'groups': [
                {
                    'group': g.group,
                    'passed': g.passed,
                    'score': round(g.score, 2),
                    'max_score': g.max_score,
                    'message': g.message,
                    'details': g.details,
                }
                for g in self.groups
            ],
            'error': self.error,
        }


# ------------------------------------------------------------------ #
# Grader                                                              #
# ------------------------------------------------------------------ #

class Grader:
    """
    Chấm bài AI qua Judge0.

    Quy trình:
    1. Gửi code lên Judge0 với từng test input.
    2. Nhận stdout, kiểm tra theo từng nhóm.
    3. Tổng hợp điểm.

    KHÔNG dùng trạng thái Accepted của Judge0 làm điểm cuối cùng.
    """

    # Trọng số điểm mỗi nhóm (tổng = 100)
    GROUP_MAX_SCORES = {
        'execution':     15.0,
        'protocol':      20.0,
        'legal_move':    30.0,
        'runtime_limit': 10.0,
        'robustness':    10.0,
        'simulation':    15.0,
    }

    def __init__(self, client: Optional[Judge0Client] = None):
        if client is None:
            from judge.client import get_client
            client = get_client()
        self.client = client
        self._language_id: Optional[int] = None

    def _get_language_id(self) -> int:
        if self._language_id is None:
            self._language_id = self.client.get_python3_language_id()
        return self._language_id

    # ---------------------------------------------------------------- #
    # Public: grade                                                     #
    # ---------------------------------------------------------------- #

    def grade(self, submission_id: int, source_code: str) -> GradingReport:
        """
        Chấm bài và trả GradingReport.
        submission_id chỉ để gắn vào report, không query DB.
        """
        report = GradingReport(
            submission_id=submission_id,
            total_score=0.0,
            max_score=sum(self.GROUP_MAX_SCORES.values()),
        )

        # Lấy language_id một lần
        try:
            lang_id = self._get_language_id()
        except Judge0Error as e:
            report.error = f'Không thể xác định Python language ID: {e}'
            return report

        test_states = _make_test_states()

        # --- Nhóm 1: Execution ------------------------------------------
        exec_result = self._grade_execution(source_code, test_states[0]['state'], lang_id)
        report.groups.append(exec_result)
        report.total_score += exec_result.score

        # Nếu execution hoàn toàn thất bại → dừng sớm, không thể chấm tiếp
        if not exec_result.passed:
            report.groups.extend([
                GroupResult(group, False, 0, ms,
                            'Bỏ qua: code không thực thi được')
                for group, ms in list(self.GROUP_MAX_SCORES.items())[1:]
            ])
            return report

        # --- Nhóm 2: Protocol -------------------------------------------
        proto_result = self._grade_protocol(source_code, test_states, lang_id)
        report.groups.append(proto_result)
        report.total_score += proto_result.score

        # --- Nhóm 3: Legal Move -----------------------------------------
        legal_result = self._grade_legal_move(source_code, test_states, lang_id)
        report.groups.append(legal_result)
        report.total_score += legal_result.score

        # --- Nhóm 4: Runtime Limit --------------------------------------
        runtime_result = self._grade_runtime_limit(source_code, test_states[0]['state'], lang_id)
        report.groups.append(runtime_result)
        report.total_score += runtime_result.score

        # --- Nhóm 5: Robustness -----------------------------------------
        robust_result = self._grade_robustness(source_code, lang_id)
        report.groups.append(robust_result)
        report.total_score += robust_result.score

        # --- Nhóm 6: Simulation -----------------------------------------
        sim_result = self._grade_simulation(source_code, lang_id)
        report.groups.append(sim_result)
        report.total_score += sim_result.score

        return report

    # ---------------------------------------------------------------- #
    # Nhóm 1: Execution                                                 #
    # ---------------------------------------------------------------- #

    def _grade_execution(self, source_code: str, state: GameState, lang_id: int) -> GroupResult:
        """Kiểm tra Python có chạy được không."""
        max_score = self.GROUP_MAX_SCORES['execution']
        stdin = json.dumps(build_ai_input(state))

        try:
            result = self.client.submit_and_wait(source_code, stdin, lang_id)
        except Judge0Unavailable as e:
            return GroupResult(
                group='execution', passed=False, score=0, max_score=max_score,
                message=f'Judge0 không khả dụng: {e}',
            )
        except Judge0Error as e:
            return GroupResult(
                group='execution', passed=False, score=0, max_score=max_score,
                message=f'Lỗi Judge0: {e}',
            )

        if result.compile_output:
            return GroupResult(
                group='execution', passed=False, score=0, max_score=max_score,
                message=f'Lỗi biên dịch/cú pháp: {result.compile_output[:300]}',
                details={'compile_output': result.compile_output},
            )

        if result.is_accepted:
            return GroupResult(
                group='execution', passed=True, score=max_score, max_score=max_score,
                message='Code thực thi thành công.',
                details={'time': result.time, 'memory': result.memory},
            )

        # Lỗi runtime
        return GroupResult(
            group='execution', passed=False, score=0, max_score=max_score,
            message=f'Runtime error: {result.status_description}. Stderr: {result.stderr[:200]}',
            details={'status': result.status_description, 'stderr': result.stderr[:500]},
        )

    # ---------------------------------------------------------------- #
    # Nhóm 2: Protocol                                                  #
    # ---------------------------------------------------------------- #

    def _grade_protocol(self, source_code: str, test_states: list[dict],
                         lang_id: int) -> GroupResult:
        """Kiểm tra output đúng định dạng giao thức."""
        max_score = self.GROUP_MAX_SCORES['protocol']
        passed_count = 0
        details = []

        for ts in test_states:
            stdin = json.dumps(build_ai_input(ts['state']))
            try:
                result = self._run_once(source_code, stdin, lang_id)
            except Judge0Error as e:
                details.append({'test': ts['id'], 'error': str(e)})
                continue

            move = parse_ai_output(result.stdout)
            ok = move is not None
            details.append({
                'test': ts['id'],
                'passed': ok,
                'stdout_preview': result.stdout[:100],
            })
            if ok:
                passed_count += 1

        score = max_score * passed_count / len(test_states) if test_states else 0
        return GroupResult(
            group='protocol',
            passed=passed_count == len(test_states),
            score=score,
            max_score=max_score,
            message=f'Giao thức đúng: {passed_count}/{len(test_states)} test.',
            details={'tests': details},
        )

    # ---------------------------------------------------------------- #
    # Nhóm 3: Legal Move                                                #
    # ---------------------------------------------------------------- #

    def _grade_legal_move(self, source_code: str, test_states: list[dict],
                           lang_id: int) -> GroupResult:
        """Kiểm tra nước đi có hợp lệ theo game engine không."""
        max_score = self.GROUP_MAX_SCORES['legal_move']
        passed_count = 0
        details = []

        for ts in test_states:
            state = ts['state']
            stdin = json.dumps(build_ai_input(state))
            try:
                result = self._run_once(source_code, stdin, lang_id)
            except Judge0Error as e:
                details.append({'test': ts['id'], 'error': str(e)})
                continue

            move = parse_ai_output(result.stdout)
            if move is None:
                details.append({
                    'test': ts['id'],
                    'passed': False,
                    'reason': 'Output không parse được',
                })
                continue

            validation = validate_ai_move(state, move)
            ok = validation['valid']
            details.append({
                'test': ts['id'],
                'passed': ok,
                'move': move,
                'reason': validation.get('reason', ''),
            })
            if ok:
                passed_count += 1

        score = max_score * passed_count / len(test_states) if test_states else 0
        return GroupResult(
            group='legal_move',
            passed=passed_count == len(test_states),
            score=score,
            max_score=max_score,
            message=f'Nước đi hợp lệ: {passed_count}/{len(test_states)} test.',
            details={'tests': details},
        )

    # ---------------------------------------------------------------- #
    # Nhóm 4: Runtime Limit                                             #
    # ---------------------------------------------------------------- #

    def _grade_runtime_limit(self, source_code: str, state: GameState,
                               lang_id: int) -> GroupResult:
        """Kiểm tra AI có trả lời trong thời gian cho phép không."""
        max_score = self.GROUP_MAX_SCORES['runtime_limit']
        stdin = json.dumps(build_ai_input(state))
        cpu_limit = self.client.cpu_time_limit

        try:
            result = self._run_once(source_code, stdin, lang_id)
        except Judge0Error as e:
            return GroupResult(
                group='runtime_limit', passed=False, score=0, max_score=max_score,
                message=f'Judge0 error: {e}',
            )

        # Status 5 = TLE
        if result.status_id == 5:
            return GroupResult(
                group='runtime_limit', passed=False, score=0, max_score=max_score,
                message=f'Vượt giới hạn thời gian {cpu_limit}s.',
                details={'time': result.time, 'wall_time': result.wall_time},
            )

        if result.is_accepted:
            t = result.time or 0
            return GroupResult(
                group='runtime_limit', passed=True, score=max_score, max_score=max_score,
                message=f'Thời gian OK: {t:.3f}s / {cpu_limit}s.',
                details={'time': t, 'memory': result.memory},
            )

        return GroupResult(
            group='runtime_limit', passed=False, score=max_score * 0.5, max_score=max_score,
            message=f'Lỗi runtime: {result.status_description}.',
        )

    # ---------------------------------------------------------------- #
    # Nhóm 5: Robustness                                                #
    # ---------------------------------------------------------------- #

    def _grade_robustness(self, source_code: str, lang_id: int) -> GroupResult:
        """
        Kiểm tra AI xử lý đúng khi:
        - Trạng thái không có nước đi (game_over=True)
        - Input có cấu trúc nhưng legal_moves rỗng
        """
        max_score = self.GROUP_MAX_SCORES['robustness']
        passed_count = 0
        details = []
        tests = []

        # Test: game_over state
        state_over = GameState()
        state_over.game_over = True
        state_over.winner = 1
        ai_input_over = build_ai_input(state_over)
        tests.append({
            'id': 'game_over',
            'description': 'game_over=True, legal_moves rỗng',
            'stdin': json.dumps(ai_input_over),
            'expect': 'any_output',  # Không crash là đủ
        })

        # Test: legal_moves rỗng (all pieces blocked hypothetically)
        state_empty_moves = GameState()
        ai_input_empty = build_ai_input(state_empty_moves)
        ai_input_empty['legal_moves'] = []
        tests.append({
            'id': 'empty_moves',
            'description': 'legal_moves rỗng',
            'stdin': json.dumps(ai_input_empty),
            'expect': 'any_output',
        })

        for test in tests:
            try:
                result = self._run_once(source_code, test['stdin'], lang_id)
                # Không crash = passed
                ok = result.is_accepted
                details.append({
                    'test': test['id'],
                    'passed': ok,
                    'description': test['description'],
                    'status': result.status_description,
                })
                if ok:
                    passed_count += 1
            except Judge0Error as e:
                details.append({'test': test['id'], 'error': str(e)})

        score = max_score * passed_count / len(tests) if tests else 0
        return GroupResult(
            group='robustness',
            passed=passed_count == len(tests),
            score=score,
            max_score=max_score,
            message=f'Robustness: {passed_count}/{len(tests)} test không crash.',
            details={'tests': details},
        )

    # ---------------------------------------------------------------- #
    # Nhóm 6: Simulation                                                #
    # ---------------------------------------------------------------- #

    def _grade_simulation(self, source_code: str, lang_id: int) -> GroupResult:
        """
        Chạy AI qua một trận đấu ngắn (tối đa 20 lượt).
        AI đóng vai P1, random opponent đóng vai P2.
        Điểm: số nước đi hợp lệ / tổng lượt.
        """
        max_score = self.GROUP_MAX_SCORES['simulation']
        import random

        state = GameState()
        total_turns = 0
        valid_turns = 0
        max_sim_turns = 20
        details = []

        while not state.game_over and total_turns < max_sim_turns:
            if state.current_player == 1:
                # AI đóng vai P1
                stdin = json.dumps(build_ai_input(state))
                try:
                    result = self._run_once(source_code, stdin, lang_id)
                except Judge0Error:
                    details.append({'turn': total_turns + 1, 'error': 'Judge0 error'})
                    break

                move = parse_ai_output(result.stdout)
                if move is None:
                    details.append({
                        'turn': total_turns + 1,
                        'player': 1,
                        'valid': False,
                        'reason': 'Output không parse được',
                    })
                    total_turns += 1
                    break

                validation = validate_ai_move(state, move)
                total_turns += 1
                if validation['valid']:
                    state.execute_move(
                        move['from_row'], move['from_col'],
                        move['to_row'], move['to_col'],
                    )
                    valid_turns += 1
                    details.append({'turn': total_turns, 'player': 1, 'valid': True, 'move': move})
                else:
                    details.append({
                        'turn': total_turns,
                        'player': 1,
                        'valid': False,
                        'reason': validation['reason'],
                    })
                    break  # AI đi sai → dừng simulation

            else:
                # P2: random AI (đơn giản để test)
                legal = state.get_all_legal_moves()
                if not legal:
                    break
                move = random.choice(legal)
                state.execute_move(
                    move['from_row'], move['from_col'],
                    move['to_row'], move['to_col'],
                )
                total_turns += 1
                valid_turns += 1

        if total_turns == 0:
            score = 0
        else:
            ratio = valid_turns / total_turns
            score = max_score * ratio

        return GroupResult(
            group='simulation',
            passed=valid_turns == total_turns and total_turns > 0,
            score=round(score, 2),
            max_score=max_score,
            message=(
                f'Simulation: {valid_turns}/{total_turns} lượt hợp lệ. '
                f'Game over: {state.game_over}, winner: {state.winner}.'
            ),
            details={
                'total_turns': total_turns,
                'valid_turns': valid_turns,
                'game_over': state.game_over,
                'winner': state.winner,
                'turns': details[:10],  # Giới hạn để không quá dài
            },
        )

    # ---------------------------------------------------------------- #
    # Helper                                                            #
    # ---------------------------------------------------------------- #

    def _run_once(self, source_code: str, stdin: str, lang_id: int) -> Judge0Result:
        """Submit và poll kết quả một lần."""
        return self.client.submit_and_wait(source_code, stdin, lang_id)
