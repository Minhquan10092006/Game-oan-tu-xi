from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from web.models import Season, TournamentRound


class Command(BaseCommand):
    help = 'Tạo khung vòng bảng đến chung kết cho một mùa giải chưa có vòng.'

    def add_arguments(self, parser):
        parser.add_argument('season_id', type=int)
        parser.add_argument('--with-round-of-32', action='store_true')

    def handle(self, *args, **options):
        with transaction.atomic():
            try:
                season = Season.objects.select_for_update().get(pk=options['season_id'])
            except Season.DoesNotExist as exc:
                raise CommandError('Không tìm thấy mùa giải.') from exc
            if season.rounds.exists():
                raise CommandError('Mùa giải đã có vòng; không tự ghi đè lịch hiện có.')
            stages = [('group', 'Vòng bảng', 'Hai lượt, tính điểm 3–1–0', 2)]
            if options['with_round_of_32']:
                stages.append(('round_of_32', 'Vòng 32', 'Loại trực tiếp', 0))
            stages += [
                ('round_of_16', 'Vòng 16', 'Loại trực tiếp', 0),
                ('quarterfinal', 'Tứ kết', 'Loại trực tiếp', 0),
                ('semifinal', 'Bán kết', 'Loại trực tiếp', 0),
                ('third_place', 'Tranh hạng ba', 'Loại trực tiếp', 0),
                ('final', 'Chung kết', 'Loại trực tiếp', 0),
            ]
            TournamentRound.objects.bulk_create([
                TournamentRound(season=season, stage=stage, order=index, name=name,
                                format_note=note, advance_count=advance)
                for index, (stage, name, note, advance) in enumerate(stages, 1)
            ])
        self.stdout.write(self.style.SUCCESS(f'Đã tạo {len(stages)} vòng cho {season.name}.'))
