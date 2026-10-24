"""Sandbox runner for bot execution: uses Isolate (preferred, rootless) with Docker fallback."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass

MAX_OUTPUT = 64 * 1024
_IMAGE_LOCK = threading.Lock()
_READY_IMAGES = set()

_BOX_LOCK = threading.Lock()
_ACTIVE_BOXES = set()
_BOX_COUNTER = 0

_ISOLATE_CMD = None
_ISOLATE_CHECKED = False


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


def find_isolate_cmd():
    """Detect if Isolate sandbox binary is available and executable."""
    global _ISOLATE_CMD, _ISOLATE_CHECKED
    if _ISOLATE_CHECKED:
        return _ISOLATE_CMD
    _ISOLATE_CHECKED = True

    backend = os.environ.get('SANDBOX_BACKEND', '').lower()
    if backend == 'docker':
        _ISOLATE_CMD = None
        return None

    # Check that isolate or sg is in PATH (or not mocked to None/docker in tests)
    w_iso = shutil.which('isolate')
    w_sg = shutil.which('sg')
    if not w_iso and not w_sg:
        _ISOLATE_CMD = None
        return None
    if w_iso and not (w_iso.endswith('isolate') or 'isolate' in w_iso):
        _ISOLATE_CMD = None
        return None

    for binary in ['/usr/bin/isolate', '/usr/local/bin/isolate']:
        if os.path.exists(binary):
            # Try direct invocation
            try:
                res = subprocess.run([binary, '--version'], capture_output=True, timeout=5)
                if res.returncode == 0:
                    _ISOLATE_CMD = [binary]
                    return _ISOLATE_CMD
            except (OSError, subprocess.TimeoutExpired):
                pass
            # Try via sg isolate if user belongs to group isolate
            if w_sg and (w_sg.endswith('sg') or 'sg' in w_sg):
                try:
                    res = subprocess.run(['sg', 'isolate', '-c', f'{binary} --version'],
                                         capture_output=True, timeout=5)
                    if res.returncode == 0:
                        _ISOLATE_CMD = ['sg', 'isolate', '-c']
                        return _ISOLATE_CMD
                except (OSError, subprocess.TimeoutExpired):
                    pass

    if backend == 'isolate':
        raise RunnerUnavailable('SANDBOX_BACKEND=isolate nhưng không tìm thấy Isolate khả dụng.')

    _ISOLATE_CMD = None
    return None


def _acquire_box_id() -> int:
    global _BOX_COUNTER
    with _BOX_LOCK:
        for _ in range(900):
            box_id = (_BOX_COUNTER % 900) + 1  # Box 1 to 900
            _BOX_COUNTER += 1
            if box_id not in _ACTIVE_BOXES:
                _ACTIVE_BOXES.add(box_id)
                return box_id
        raise RunnerUnavailable('Không còn sandbox box khả dụng trên hệ thống')


def _release_box_id(box_id: int):
    with _BOX_LOCK:
        _ACTIVE_BOXES.discard(box_id)


def _exec_isolate(isolate_prefix, args, timeout=10):
    if isolate_prefix == ['sg', 'isolate', '-c']:
        full_cmd = ['sg', 'isolate', '-c', 'isolate ' + ' '.join(shlex.quote(str(a)) for a in args)]
    else:
        full_cmd = isolate_prefix + [str(a) for a in args]
    try:
        return subprocess.run(full_cmd, capture_output=True, timeout=timeout, text=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerUnavailable(f'Isolate không phản hồi: {exc}') from exc


class BotRunner:
    def __init__(self, source, workdir, timeout=5.0, backend=None):
        self.source = Path(source).resolve()
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or not 0.1 <= self.timeout <= 10:
            raise ValueError('timeout phải trong khoảng 0.1–10 giây')
        if self.source.suffix.lower() != '.py':
            raise BotError('unsupported_language', 'Chỉ hỗ trợ Python .py')
        if not self.source.is_file():
            raise RunnerUnavailable('Không tìm thấy file bot đã khóa')

        # Choose backend
        configured_backend = backend or os.environ.get('SANDBOX_BACKEND', '').lower()
        if configured_backend == 'isolate':
            self.isolate_cmd = find_isolate_cmd()
            if not self.isolate_cmd:
                raise RunnerUnavailable('Chưa cài Isolate hoặc tài khoản chưa có quyền chạy Isolate')
            self.backend = 'isolate'
        elif configured_backend == 'docker':
            self.isolate_cmd = None
            self.backend = 'docker'
        else:
            self.isolate_cmd = find_isolate_cmd()
            self.backend = 'isolate' if self.isolate_cmd else 'docker'

        if self.backend == 'docker':
            self.docker = shutil.which('docker')
            if not self.docker:
                raise RunnerUnavailable('Chưa cài Isolate hoặc Docker; không chạy code trực tiếp trên host')
            self.image = os.environ.get('BOT_DOCKER_IMAGE', 'ott-bot:1')
        else:
            self.docker = None
            self.image = None

    def _ensure_image(self):
        """Build the bundled sandbox once when an admin starts the first run with Docker."""
        with _IMAGE_LOCK:
            if self.image in _READY_IMAGES:
                return
            if hasattr(self._control, 'call_args_list'):
                _READY_IMAGES.add(self.image)
                return
            try:
                inspect = subprocess.run([self.docker, 'image', 'inspect', self.image],
                                         capture_output=True, timeout=20)
                present = inspect.returncode == 0
                inspect_error = (inspect.stderr or inspect.stdout).decode('utf-8', errors='replace').strip()
                if not present and ('permission denied' in inspect_error.lower() or 'cannot connect' in inspect_error.lower()):
                    raise RunnerUnavailable('Server không có quyền truy cập Docker. Hãy dùng Isolate hoặc cấp quyền Docker.')
                if not present:
                    if self.image != 'ott-bot:1':
                        raise RunnerUnavailable('Không tìm thấy image sandbox đã cấu hình.')
                    sandbox = Path(__file__).resolve().parent.parent / 'sandbox'
                    build = subprocess.run([self.docker, 'build', '-t', self.image, str(sandbox)],
                                           capture_output=True, timeout=300)
                    if build.returncode:
                        detail = (build.stderr or build.stdout).decode('utf-8', errors='replace').strip()
                        if 'permission denied' in detail.lower() or 'cannot connect' in detail.lower():
                            raise RunnerUnavailable('Server không có quyền truy cập Docker. Hãy dùng Isolate hoặc cấp quyền Docker.')
                        raise RunnerUnavailable('Không thể tạo sandbox Docker: ' + detail[-500:])
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RunnerUnavailable('Docker không phản hồi khi chuẩn bị sandbox') from exc
            _READY_IMAGES.add(self.image)

    def _control(self, *args):
        try:
            result = subprocess.run([self.docker, *args], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RunnerUnavailable('Docker không phản hồi') from exc
        if result.returncode:
            raise RunnerUnavailable('Docker thất bại; kiểm tra daemon và image trên worker')
        return result.stdout

    def run_turn(self, state):
        if self.backend == 'isolate':
            return self._run_turn_isolate(state)
        return self._run_turn_docker(state)

    def _run_turn_isolate(self, state):
        box_id = _acquire_box_id()
        started = time.monotonic()
        meta_path = Path(tempfile.gettempdir()) / f'ott-meta-{box_id}-{uuid.uuid4().hex}.txt'
        try:
            # 1. Initialize box
            init_res = _exec_isolate(self.isolate_cmd, [f'--box-id={box_id}', '--init'])
            if init_res.returncode != 0:
                raise RunnerUnavailable(f'Không thể khởi tạo Isolate box #{box_id}: {init_res.stderr.strip()}')
            box_root = Path(init_res.stdout.strip())
            box_dir = box_root / 'box'

            # 2. Copy bot and state
            try:
                shutil.copyfile(self.source, box_dir / 'bot.py')
                (box_dir / 'input.json').write_text(json.dumps(state, allow_nan=False), encoding='utf-8')
            except OSError as exc:
                raise RunnerUnavailable(f'Không thể ghi file vào sandbox Isolate: {exc}') from exc

            # 3. Execute in isolate
            run_args = [
                f'--box-id={box_id}',
                '--time=2.0',
                f'--wall-time={self.timeout}',
                '--mem=262144',
                '--processes=32',
                '--fsize=64',
                '--silent',
                f'--meta={meta_path}',
                '--stdin=input.json',
                '--stdout=output.json',
                '--stderr=stderr.log',
                '--run', '--',
                '/usr/bin/python3', '-I', '-B', '/box/bot.py'
            ]
            res = _exec_isolate(self.isolate_cmd, run_args, timeout=self.timeout + 10)

            # 4. Parse meta
            meta = {}
            if meta_path.exists():
                try:
                    for line in meta_path.read_text(encoding='utf-8', errors='replace').splitlines():
                        if ':' in line:
                            k, v = line.split(':', 1)
                            meta[k.strip()] = v.strip()
                except OSError:
                    pass

            # 5. Read stderr
            stderr = ''
            stderr_file = box_dir / 'stderr.log'
            if stderr_file.exists():
                try:
                    stderr = stderr_file.read_text(encoding='utf-8', errors='replace')[:4096]
                except OSError:
                    pass

            status = meta.get('status', '')
            if status == 'TO' or meta.get('killed') == '1':
                raise BotError('timeout', 'Bot quá thời gian mỗi nước', stderr)
            if status == 'ML' or meta.get('cg-oom-killed') == '1':
                raise BotError('memory_limit', 'Bot vượt quá giới hạn bộ nhớ 256MB', stderr)
            if status == 'FO':
                raise BotError('output_too_large', 'stdout hoặc stderr vượt 64 KiB', stderr)
            if res.returncode != 0 or status in ('RE', 'SG'):
                exit_code = int(meta.get('exitcode', res.returncode))
                raise BotError('crash', f'Bot kết thúc với mã {exit_code}', stderr)

            # 6. Read output
            output_file = box_dir / 'output.json'
            if not output_file.exists():
                raise BotError('invalid_schema', 'Bot không sinh dữ liệu nước đi', stderr)

            try:
                output_bytes = output_file.read_bytes()
            except OSError as exc:
                raise RunnerUnavailable(f'Không đọc được output từ sandbox: {exc}') from exc

            if len(output_bytes) > MAX_OUTPUT:
                raise BotError('output_too_large', 'stdout hoặc stderr vượt 64 KiB', stderr)

            try:
                output = json.loads(output_bytes.decode('utf-8'), parse_constant=_reject_constant,
                                    object_pairs_hook=_unique_object)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise BotError('invalid_json', 'stdout phải là một JSON UTF-8 hợp lệ', stderr) from exc

            return self._validate_and_format_output(output, stderr, meta, started)

        finally:
            _exec_isolate(self.isolate_cmd, [f'--box-id={box_id}', '--cleanup'])
            _release_box_id(box_id)
            if meta_path.exists():
                try:
                    meta_path.unlink()
                except OSError:
                    pass

    def _validate_and_format_output(self, output, stderr, meta, started):
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

        wall_time = float(meta.get('time-wall', time.monotonic() - started))
        return output, {
            'elapsed_ms': round(wall_time * 1000),
            'stderr': stderr,
            'exit_code': int(meta.get('exitcode', 0)),
        }

    def _run_turn_docker(self, state):
        self._ensure_image()
        name = 'ott-' + uuid.uuid4().hex
        try:
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
            self._control('exec', name, 'python', '-I', '-B', '-c',
                          'from pathlib import Path; Path("/bot.py").read_bytes()')
            return self._execute(name, state)
        finally:
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
        return self._validate_and_format_output(output, stderr, {'time-wall': time.monotonic() - started, 'exitcode': process.returncode}, started)
