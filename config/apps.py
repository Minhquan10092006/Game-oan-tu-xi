"""
config/apps.py
--------------
AppConfig cho config app - bật SQLite WAL mode khi production.
"""
import os
from django.apps import AppConfig


class ConfigConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'config'

    def ready(self):
        # Chỉ bật WAL mode khi KHÔNG phải DEBUG (production)
        if os.environ.get('DJANGO_DEBUG', 'True').lower() in ('1', 'true', 'yes'):
            return

        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA journal_mode=WAL;')
                cursor.execute('PRAGMA synchronous=NORMAL;')
                cursor.execute('PRAGMA cache_size=-32768;')  # 32MB cache
                cursor.execute('PRAGMA temp_store=MEMORY;')
                cursor.execute('PRAGMA busy_timeout=30000;')  # 30s
        except Exception:
            pass  # Fail silently