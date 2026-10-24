"""Generate a separate rehearsal season; never fabricate official match results."""
import hashlib
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from submissions.models import Submission
from web.models import Season, CompetitionEntry, OfficialBot, UserProfile
from web.tournament import draw_season
from web.tournament_ops import transition, enqueue_validation

SOURCE = "import json,sys\ns=json.load(sys.stdin)\nprint(json.dumps({'move':s['legal_moves'][0]}))\n"


class Command(BaseCommand):
    help = 'Tạo mùa diễn tập riêng, tài khoản không đăng nhập được và bot mẫu. Chỉ dùng môi trường DEBUG.'

    def add_arguments(self, parser):
        parser.add_argument('--participants', type=int, default=16)
        parser.add_argument('--image', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Chỉ tạo dữ liệu giả trên môi trường staging/local có DEBUG=True.')
        count = options['participants']
        if not 2 <= count <= 4000:
            raise CommandError('Số người diễn tập phải từ 2 đến 4000.')
        prefix = 'rehearsal-' + uuid.uuid4().hex[:10]
        user_model = get_user_model()
        users = user_model.objects.bulk_create([user_model(username=f'{prefix}-{i}', password='!') for i in range(count)])
        UserProfile.objects.bulk_create([UserProfile(user=user) for user in users])
        season = Season.objects.create(name=f'DIỄN TẬP {prefix} ({count})', start_date=timezone.localdate(),
                                       phase='submission', judge_image=options['image'])
        entries = CompetitionEntry.objects.bulk_create([CompetitionEntry(season=season, user=user, display_name=user.username) for user in users])
        submissions = Submission.objects.bulk_create([Submission(submitter=user, competition_entry=entry, ai_name='Rehearsal', source_code=SOURCE) for user, entry in zip(users, entries)])
        OfficialBot.objects.bulk_create([OfficialBot(entry=entry, submission=submission, source_code=SOURCE, sha256=hashlib.sha256(SOURCE.encode()).hexdigest()) for entry, submission in zip(entries, submissions)])
        transition(season.pk, 'locked', None)
        enqueue_validation(season.pk, None)
        draw = draw_season(season.pk)
        self.stdout.write(f'Mùa diễn tập #{season.pk}: {count} bài, {draw["group_count"]} bảng. Chưa chạy bot hay tạo kết quả giả. Mở /tournament/ và kết nối máy chấm để đo thực tế.')
