"""Serve LAN web and consume the persistent judge queue on one computer."""
import ipaddress
import logging
import os
import shutil
import subprocess
import threading

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def check_sandbox():
    from matches.bot_runner import find_isolate_cmd, RunnerUnavailable
    try:
        if find_isolate_cmd():
            return 'Isolate'
    except RunnerUnavailable as exc:
        raise CommandError(str(exc)) from exc
    if os.environ.get('SANDBOX_BACKEND', '').lower() == 'isolate':
        raise CommandError('Đã chọn Isolate nhưng Isolate chưa sẵn sàng.')
    docker = shutil.which('docker')
    if not docker:
        raise CommandError('Chưa có Isolate/Docker. Cài sandbox trước khi tổ chức giải.')
    for args in [('info',), ('image', 'inspect', settings.TOURNAMENT_DOCKER_IMAGE),
                 *((('image', 'inspect', settings.PRACTICE_DOCKER_IMAGE),)
                   if settings.PRACTICE_DOCKER_IMAGE else ())]:
        try:
            result = subprocess.run([docker, *args], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CommandError('Docker chưa sẵn sàng. Hãy mở Docker Desktop.') from exc
        if result.returncode:
            raise CommandError('Docker chưa chạy hoặc thiếu image. Khi còn Internet, chạy: '
                               'docker build -t ott-bot:1 sandbox '
                               '(nếu dùng image khác, chuẩn bị đúng image đó trước).')
    return 'Docker (image đã có sẵn)'


class Command(BaseCommand):
    help = 'Chạy web và bộ chấm trong LAN; dùng qua run_classroom.py.'

    def add_arguments(self, parser):
        parser.add_argument('--address', required=True, help='IPv4 LAN của máy giáo viên, xem bằng ipconfig.')
        parser.add_argument('--port', type=int, default=8000)
        parser.add_argument('--check-only', action='store_true', help='Kiểm tra sandbox và cấu hình, chưa mở web.')

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != 'config.classroom_settings':
            raise CommandError('Hãy dùng: python run_classroom.py --address <IP LAN>')
        try:
            address = ipaddress.IPv4Address(options['address'])
        except ipaddress.AddressValueError as exc:
            raise CommandError('Địa chỉ IPv4 không hợp lệ.') from exc
        if address.is_unspecified or address.is_multicast or not 1 <= options['port'] <= 65535:
            raise CommandError('Dùng IP LAN cụ thể và cổng từ 1 đến 65535.')
        settings.ALLOWED_HOSTS = ['localhost', '127.0.0.1', str(address)]
        self.check()
        sandbox = check_sandbox()
        self.stdout.write(f'Sandbox: {sandbox}. Database lưu trên máy giáo viên.')
        if options['check_only']:
            self.stdout.write('Kiểm tra cấu hình đạt. Vẫn cần thử nộp và chấm khi ngắt Internet.')
            return
        call_command('migrate', interactive=False, verbosity=0)
        call_command('collectstatic', interactive=False, verbosity=0)
        stop = threading.Event()

        def consume():
            from web.local_judge import run_once
            while not stop.is_set():
                try:
                    if run_once():
                        continue
                except Exception:
                    logger.exception('Bộ chấm tạm lỗi; giữ hàng đợi và thử lại sau.')
                finally:
                    close_old_connections()
                stop.wait(2)

        worker = threading.Thread(target=consume, daemon=True, name='classroom-judge')
        worker.start()
        self.stdout.write(self.style.SUCCESS(f'Sinh viên truy cập: http://{address}:{options["port"]}/'))
        self.stdout.write('Giữ cửa sổ này và sandbox chạy. Ctrl+C để dừng. Không cần Internet, cần LAN.')
        try:
            call_command('runserver', f'0.0.0.0:{options["port"]}', use_reloader=False)
        finally:
            stop.set()
            worker.join(timeout=5)
