"""Remote worker: python -m matches.judge_worker --server https://example.org

Set JUDGE_WORKER_TOKEN separately on each of the four dedicated Docker machines.
No Django or database credentials are needed on these machines.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .bot_runner import BotRunner, BotError, RunnerUnavailable
from .game_engine import GameState, board_presets
from .match_manager import MatchManager
from .tournament import engine_hash


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Worker API không được chuyển hướng; kiểm tra URL server.')


class Coordinator:
    def __init__(self, server, token):
        parsed = urllib.parse.urlparse(server)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))):
            raise ValueError('Dùng HTTPS; HTTP chỉ cho localhost khi phát triển.')
        self.base, self.token = server.rstrip('/'), token
        self.opener = urllib.request.build_opener(NoRedirect)

    def post(self, action, payload):
        data = json.dumps(payload, allow_nan=False).encode()
        request = urllib.request.Request(f'{self.base}/api/competition/workers/{action}/', data=data,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=30) as response:
            return json.load(response)


def validate_bot(path):
    """Smoke tests for every preset and both sides; never execute Python on the host."""
    passed = 0
    for preset in board_presets().values():
        for player in ('P1', 'P2'):
            state = GameState(preset, 300)
            state.current_player = player
            output, _ = BotRunner(path, path.parent, 5).run_turn(state.bot_input('preflight', None))
            state.apply_move(output['move'])
            passed += 1
    return {'valid': True, 'tests_passed': passed, 'message': f'Đạt {passed} kiểm tra giao thức và nước đi; chưa bảo đảm mọi tình huống thi đấu.'}


def execute(job):
    os.environ['BOT_DOCKER_IMAGE'] = job['image']
    with tempfile.TemporaryDirectory(prefix='ott-judge-') as directory:
        paths = []
        for number, bot in enumerate(job['bots']):
            data = bot['source'].encode('utf-8')
            path = Path(directory) / f'bot-{number}.py'
            path.write_bytes(data)
            paths.append(path)
        if job['kind'] == 'validation':
            try:
                return validate_bot(paths[0])
            except (BotError, ValueError) as exc:
                message = exc.message if isinstance(exc, BotError) else str(exc)
                return {'valid': False, 'message': message, 'error': getattr(exc, 'code', 'illegal_move')}
        result = MatchManager().run(*paths, match_id=f"job-{job['id']}")
        if result['result'] == 'error':
            return {'infrastructure_error': True, 'message': 'Lỗi máy chấm; cần kiểm tra và chạy lại.', 'replay': result}
        return result


def process_job(client, job):
    stop = threading.Event()
    lost = threading.Event()
    lease = {'job_id': job['id'], 'lease_token': job['lease_token']}

    def keep_alive():
        while not stop.wait(25):
            try:
                client.post('heartbeat', lease)
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 409):
                    lost.set()
                    return
            except (OSError, ValueError):
                # A temporary network failure may recover before the lease expires.
                continue

    heartbeat = threading.Thread(target=keep_alive, daemon=True)
    heartbeat.start()
    try:
        try:
            result = execute(job)
        except Exception as exc:
            result = {'infrastructure_error': True, 'message': f'{type(exc).__name__}: {exc}'[:2000]}
        if lost.is_set():
            print(f"Job {job['id']}: hết hạn giữ chỗ; bỏ kết quả cũ.", flush=True)
            return
        for attempt in range(3):
            try:
                client.post('finish', {**lease, 'result': result})
                print(f"Job {job['id']}: đã gửi kết quả", flush=True)
                return
            except urllib.error.HTTPError:
                raise
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(2)
    finally:
        stop.set()
        heartbeat.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description='Một máy chấm Docker nhận việc từ hàng đợi giải đấu.')
    parser.add_argument('--server', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    token = os.environ.get('JUDGE_WORKER_TOKEN')
    if not token:
        parser.error('Cần biến môi trường JUDGE_WORKER_TOKEN của máy này.')
    client = Coordinator(args.server, token)
    while True:
        try:
            job = client.post('claim', {'engine': engine_hash()})['job']
            if job:
                process_job(client, job)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f'Chưa chấm được: {type(exc).__name__}. Kiểm tra server, token, engine và kết nối.', flush=True)
        if args.once:
            break
        time.sleep(5)


if __name__ == '__main__':
    main()
