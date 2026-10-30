from django.core.management.base import BaseCommand
from django.conf import settings
from web.local_judge import run_until_empty


class Command(BaseCommand):
    help = 'Chạy hàng đợi sandbox trên chính server; không cần token hay worker riêng.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true', help='Chờ và xử lý việc mới liên tục.')

    def handle(self, *args, **options):
        db_name = settings.DATABASES['default'].get('NAME', '')
        db_engine = settings.DATABASES['default'].get('ENGINE', '').split('.')[-1]
        self.stdout.write(self.style.SUCCESS("🚀 Máy chấm (Judge Worker) đã khởi động thành công!"))
        self.stdout.write(f"📡 Database đang lắng nghe: {db_engine} ({db_name})")
        if options['watch']:
            self.stdout.write("⏳ Đang quét và lắng nghe hàng đợi ván đấu liên tục... (Nhấn Ctrl+C để dừng)")
        run_until_empty(wait=options['watch'])
