from django.core.management.base import BaseCommand
from web.local_judge import run_until_empty


class Command(BaseCommand):
    help = 'Chạy hàng đợi sandbox trên chính server; không cần token hay worker riêng.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true', help='Chờ và xử lý việc mới liên tục.')

    def handle(self, *args, **options):
        run_until_empty(wait=options['watch'])
