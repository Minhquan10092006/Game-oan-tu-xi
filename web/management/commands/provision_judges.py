import hashlib
import secrets
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group, Permission
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from web.models import JudgeWorker, JudgingJob


class Command(BaseCommand):
    help = 'Tạo 4 vị trí máy chấm và nhóm quyền. Token chỉ được in khi tạo/đổi.'

    def add_arguments(self, parser):
        parser.add_argument('--rotate-slot', type=int, choices=range(1, 5))
        parser.add_argument('--disable-slot', type=int, choices=range(1, 5))
        parser.add_argument('--operator', action='append', default=[], help='Tên tài khoản được cấp quyền điều hành.')
        parser.add_argument('--referee', action='append', default=[], help='Tên tài khoản được cấp quyền trọng tài.')

    @transaction.atomic
    def handle(self, *args, **options):
        for group_name, codename in [('Điều hành giải', 'operate_tournament'), ('Trọng tài', 'referee_tournament')]:
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.add(Permission.objects.get(content_type__app_label='web', codename=codename))
            for username in options['operator' if codename == 'operate_tournament' else 'referee']:
                try:
                    user = get_user_model().objects.get(username=username)
                except get_user_model().DoesNotExist as exc:
                    raise CommandError(f'Không tìm thấy tài khoản {username}.') from exc
                user.groups.add(group)
        for slot in range(1, 5):
            worker = JudgeWorker.objects.select_for_update().filter(slot=slot).first()
            rotate = options['rotate_slot'] == slot
            disable = options['disable_slot'] == slot
            if (rotate or disable) and worker and JudgingJob.objects.filter(worker=worker, state='running', lease_until__gt=timezone.now()).exists():
                raise CommandError('Chờ tác vụ hoàn tất/hết hạn trước khi đổi hoặc vô hiệu hóa token.')
            if disable:
                if worker:
                    worker.enabled = False
                    worker.save(update_fields=['enabled'])
                continue
            if worker and not rotate:
                self.stdout.write(f'Máy {slot}: đã tồn tại, giữ nguyên token.')
                continue
            token = secrets.token_urlsafe(48)
            JudgeWorker.objects.update_or_create(slot=slot, defaults={
                'name': f'Máy chấm {slot}', 'token_hash': hashlib.sha256(token.encode()).hexdigest(), 'enabled': True,
            })
            self.stdout.write(f'Máy {slot} — JUDGE_WORKER_TOKEN={token}')
