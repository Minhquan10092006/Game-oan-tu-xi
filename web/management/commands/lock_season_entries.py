from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from web.models import Season


class Command(BaseCommand):
    help = 'Khóa đội và mục dự thi của một mùa trước khi BTC xuất bài sang máy chấm.'

    def add_arguments(self, parser):
        parser.add_argument('season_id', type=int)

    def handle(self, *args, **options):
        with transaction.atomic():
            try:
                season = Season.objects.select_for_update().get(pk=options['season_id'])
            except Season.DoesNotExist as exc:
                raise CommandError('Không tìm thấy mùa giải.') from exc
            registered = season.entries.filter(status='registered')
            count = registered.count()
            registered.update(status='locked')
            season.teams.filter(is_locked=False).update(is_locked=True)
        self.stdout.write(self.style.SUCCESS(f'Đã khóa {count} mục dự thi và đội của mùa {season.name}.'))
