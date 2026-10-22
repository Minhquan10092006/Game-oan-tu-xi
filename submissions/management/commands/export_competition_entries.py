"""Operator-only local export; no network publication or automatic selection."""
import json
import os
from pathlib import Path
import re
import tempfile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from submissions.models import Submission


class Command(BaseCommand):
    help = 'Xuất các bài đã duyệt được BTC chọn, kèm hash và biên nhận.'

    def add_arguments(self, parser):
        parser.add_argument('selections')
        parser.add_argument('destination')

    def handle(self, *args, **options):
        destination = Path(options['destination']).resolve()
        if destination.exists():
            raise CommandError('Thư mục đích đã tồn tại; không ghi đè bản xuất cũ.')
        selections = json.loads(Path(options['selections']).read_text(encoding='utf-8-sig'))
        if not isinstance(selections, list) or len(selections) < 2:
            raise CommandError('Cần ít nhất hai đội.')
        ids, submission_ids = set(), set()
        for entry in selections:
            team, sid = entry.get('team_id'), entry.get('submission_id')
            if not isinstance(team, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', team) or team in ids:
                raise CommandError('Mã đội không hợp lệ hoặc bị trùng.')
            if type(sid) is not int or sid in submission_ids:
                raise CommandError('Mỗi bài chỉ được chọn cho một đội trong bản xuất.')
            ids.add(team)
            submission_ids.add(sid)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ott-export-', dir=destination.parent) as temp:
            staging = Path(temp) / 'export'
            staging.mkdir()
            entries, receipts = [], []
            with transaction.atomic():
                for entry in selections:
                    try:
                        sub = Submission.objects.select_for_update().get(pk=entry['submission_id'], review_status='approved')
                    except Submission.DoesNotExist as exc:
                        raise CommandError(f"Bài #{entry['submission_id']} chưa được duyệt hoặc không tồn tại.") from exc
                    filename = entry['team_id'] + '.py'
                    (staging / filename).write_bytes(sub.source_code.encode('utf-8'))
                    entries.append({'team_id': entry['team_id'], 'name': entry.get('name', entry['team_id']), 'path': filename})
                    receipts.append({'team_id': entry['team_id'], 'submission_id': sub.pk,
                                     'submitter_id': sub.submitter_id, 'version': sub.version,
                                     'submitted_at': sub.submitted_at.isoformat(), 'source_sha256': sub.source_sha256})
                    sub.used_in_battle = True
                    sub.save(update_fields=['used_in_battle'])
                for filename, data in (('entries.json', entries), ('receipts.json', receipts)):
                    (staging / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.rename(staging, destination)
        self.stdout.write(self.style.SUCCESS(f'Đã xuất {len(entries)} đội vào {destination}. Đối chiếu deadline/hash trước khi freeze.'))
