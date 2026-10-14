from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('web', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='Season',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120, verbose_name='Tên mùa giải')),
                ('description', models.TextField(blank=True, verbose_name='Mô tả')),
                ('start_date', models.DateField(verbose_name='Ngày bắt đầu')),
                ('end_date', models.DateField(blank=True, null=True, verbose_name='Ngày kết thúc')),
                ('is_active', models.BooleanField(default=True, verbose_name='Đang hoạt động')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_seasons', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Mùa giải', 'verbose_name_plural': 'Mùa giải', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='MatchHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('match_id', models.CharField(max_length=64, unique=True)),
                ('board_preset', models.CharField(default='classic_9x9', max_length=60)),
                ('result', models.CharField(choices=[('p1_win','P1 thắng'),('p2_win','P2 thắng'),('draw','Hòa'),('error','Lỗi')], max_length=10)),
                ('winner', models.CharField(blank=True, max_length=10)),
                ('total_plies', models.IntegerField(default=0)),
                ('reason_code', models.CharField(blank=True, max_length=60)),
                ('reason_message', models.TextField(blank=True)),
                ('replay_data', models.TextField(blank=True)),
                ('player1_filename', models.CharField(blank=True, max_length=255)),
                ('player2_filename', models.CharField(blank=True, max_length=255)),
                ('played_at', models.DateTimeField(auto_now_add=True)),
                ('player', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='match_histories', to=settings.AUTH_USER_MODEL)),
                ('season', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='matches', to='web.season')),
            ],
            options={'verbose_name': 'Lịch sử trận đấu', 'verbose_name_plural': 'Lịch sử trận đấu', 'ordering': ['-played_at']},
        ),
    ]
