from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('web', '0013_representative_entries')]

    operations = [
        migrations.AddField(
            model_name='season', name='problem_statement',
            field=models.TextField(blank=True, verbose_name='Đặc tả đề bài'),
        ),
    ]
