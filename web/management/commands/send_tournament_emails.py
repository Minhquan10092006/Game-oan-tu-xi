from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Email giải đấu đã ngừng sử dụng; thông báo được đăng trực tiếp trên web.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        raise CommandError('Chức năng email đã bỏ. Không gửi thư từ hàng đợi cũ; dùng thông báo trên website.')
