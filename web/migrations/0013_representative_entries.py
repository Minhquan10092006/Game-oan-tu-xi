from django.db import migrations


def convert_entries(apps, schema_editor):
    Entry = apps.get_model('web', 'CompetitionEntry')
    Season = apps.get_model('web', 'Season')
    # Keep entry IDs: submissions, snapshots, fixtures and results retain their links.
    pending = list(Entry.objects.filter(team__isnull=False).select_related('team'))
    identities = set(Entry.objects.filter(user__isnull=False).values_list('season_id', 'user_id'))
    for entry in pending:
        identity = (entry.season_id, entry.team.captain_id)
        if identity in identities:
            raise RuntimeError('Một đại diện có nhiều mục trong cùng mùa. Cần đối chiếu trước khi chuyển dữ liệu; chưa xóa mục nào.')
        identities.add(identity)
    for entry in pending:
        Entry.objects.filter(pk=entry.pk).update(user_id=entry.team.captain_id, team_id=None)
    # These legacy settings no longer affect admission. Keep historical records intact.
    Season.objects.all().update(entry_mode='individual', require_verified_email=False)
    Season.objects.filter(phase='appeals').update(phase='running')


class Migration(migrations.Migration):
    dependencies = [('web', '0012_alter_season_phase')]
    operations = [migrations.RunPython(convert_entries, migrations.RunPython.noop)]
