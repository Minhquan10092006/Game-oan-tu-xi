"""Docker-only runner for a dedicated judging machine, never the web host."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass

MAX_OUTPUT = 64 * 1024


@dataclass
class BotError(Exception):
    code: str
    message: str
    stderr: str = ''


class RunnerUnavailable(RuntimeError):
    """Infrastructure failure; neither contestant is awarded points."""


def _reject_constant(value):
    raise ValueError(f'Non-finite JSON value: {value}')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


class BotRunner:
    def __init__(self, source, workdir, timeout=5.0):
        self.source = Path(source).resolve()
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or not 0.1 <= self.timeout <= 10:
            raise ValueError('timeout phải trong khoảng 0.1–10 giây')
        if self.source.suffix.lower() != '.py':
            raise BotError('unsupported_language', 'Chỉ hỗ trợ Python .py')
        if not self.source.is_file():
            raise RunnerUnavailable('Không tìm thấy file bot đã khóa')
        self.docker = shutil.which('docker')
        if not self.docker:
            raise RunnerUnavailable('Chưa cài Docker; không chạy code trực tiếp trên host')
        self.image = os.environ.get('BOT_DOCKER_IMAGE', 'ott-bot:1')

    def _control(self, *args):
        try:
            result = subprocess.run([self.docker, *args], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RunnerUnavailable('Docker không phản hồi') from exc
        if result.returncode:
            raise RunnerUnavailable('Docker thất bại; kiểm tra daemon và image trên worker')
        return result.stdout

    def run_turn(self, state):
        name = 'ott-' + uuid.uuid4().hex
        try:
            # Contestant code is only executed after startup succeeds.
            self._control(
                'create', '--pull=never', '--name', name, '--network=none',
                '--memory=256m', '--memory-swap=256m', '--cpus=1', '--pids-limit=32',
                '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--user=65534:65534', '--tmpfs=/tmp:rw,noexec,nosuid,size=8m,mode=1777',
                '--workdir=/tmp', '--log-driver=none',
                '--mount', f'type=bind,source={self.source},target=/bot.py,readonly',
                self.image, 'python', '-I', '-B', '-c', 'import time; time.sleep(60)',
            )
            self._control('start', name)
            # A bad mount/image is an operator error, not a contestant crash.
            self._control('exec', name, 'python', '-I', '-B', '-c',
                          'from pathlib import Path; Path("/bot.py").read_bytes()')
            return self._execute(name, state)
        finally:
            # Force-remove also kills descendants. Cleanup failure stops judging.
            self._control('rm', '-f', name)

    def _execute(self, name, state):
        wrapper = (
            'import os,resource; '
            'resource.setrlimit(resource.RLIMIT_CPU,(2,2)); '
            'resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536)); '
            'resource.setrlimit(resource.RLIMIT_NOFILE,(32,32)); '
            'os.execv("/usr/local/bin/python",["python","-I","-B","/bot.py"])'
        )
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                [self.docker, 'exec', '-i', name, 'python', '-I', '-B', '-c', wrapper],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise RunnerUnavailable('Không khởi chạy được Docker exec') from exc
        buffers = [bytearray(), bytearray()]
        overflow = threading.Event()

        def read_pipe(pipe, target):
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                remaining = MAX_OUTPUT - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
            pipe.close()

        def write_input():
            try:
                process.stdin.write(json.dumps(state, allow_nan=False).encode('utf-8'))
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        readers = [threading.Thread(target=read_pipe, args=(pipe, buf), daemon=True)
                   for pipe, buf in zip((process.stdout, process.stderr), buffers)]
        writer = threading.Thread(target=write_input, daemon=True)
        for thread in [*readers, writer]:
            thread.start()
        failure = None
        while process.poll() is None:
            if overflow.is_set():
                failure = ('output_too_large', 'stdout hoặc stderr vượt 64 KiB')
                break
            if time.monotonic() - started > self.timeout:
                failure = ('timeout', 'Bot quá thời gian mỗi nước')
                break
            time.sleep(0.01)
        if failure:
            try:
                self._control('kill', name)
            finally:
                process.kill()
        process.wait(timeout=10)
        for thread in [*readers, writer]:
            thread.join(timeout=2)
        if any(t.is_alive() for t in [*readers, writer]):
            raise RunnerUnavailable('Không thu hồi được luồng giao tiếp Docker')
        stderr = buffers[1].decode('utf-8', errors='replace')[:4096]
        if failure:
            raise BotError(*failure, stderr)
        if overflow.is_set():
            raise BotError('output_too_large', 'stdout hoặc stderr vượt 64 KiB', stderr)
        if process.returncode in (125, 126, 127):
            raise RunnerUnavailable('Docker exec lỗi; BTC cần kiểm tra trước khi tính điểm')
        if process.returncode:
            running = self._control('inspect', '--format={{.State.Running}}', name).strip()
            if running != b'true':
                raise RunnerUnavailable('Sandbox dừng bất thường; BTC cần kiểm tra')
            raise BotError('crash', f'Bot kết thúc với mã {process.returncode}', stderr)
        try:
            output = json.loads(buffers[0].decode('utf-8'), parse_constant=_reject_constant,
                                object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise BotError('invalid_json', 'stdout phải là một JSON UTF-8 hợp lệ', stderr) from exc
        if not isinstance(output, dict) or not isinstance(output.get('move'), dict):
            raise BotError('invalid_schema', 'Output phải có move object', stderr)
        move = output['move']
        if not isinstance(move.get('piece_id'), str) or any(
            not isinstance(move.get(key), list) or len(move[key]) != 2 or
            any(type(x) is not int for x in move[key]) for key in ('from', 'to')
        ):
            raise BotError('invalid_schema', 'move cần piece_id và from/to là hai số nguyên', stderr)
        try:
            userdata_size = len(json.dumps(output.get('userdata'), ensure_ascii=False, allow_nan=False).encode('utf-8'))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise BotError('invalid_schema', 'userdata phải tuần tự hóa được thành JSON UTF-8', stderr) from exc
        if userdata_size > 4096:
            raise BotError('userdata_too_large', 'userdata vượt 4 KiB', stderr)
        return output, {'elapsed_ms': round((time.monotonic() - started) * 1000),
                        'stderr': stderr, 'exit_code': process.returncode}
