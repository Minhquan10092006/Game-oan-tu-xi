"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application`` and ``app`` (for Vercel).

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
app = application

# Tự động khởi tạo database, migrations và tài khoản admin trên Vercel
if os.environ.get('VERCEL'):
    try:
        from django.db import connection
        tables = connection.introspection.table_names()
        if 'web_season' not in tables:
            from django.core.management import call_command
            print("Vercel: Running auto-migrations...")
            call_command('migrate', interactive=False)
            print("Vercel: Migrations completed.")
            tables = connection.introspection.table_names()

        if 'web_season' in tables:
            try:
                from web.models import Season
                from django.utils import timezone
                if not Season.objects.filter(is_active=True).exists():
                    Season.objects.create(
                        name="Mùa giải Khởi động",
                        description="Đấu trường Oẳn Tù Tì 2.0",
                        start_date=timezone.now().date(),
                        is_active=True,
                    )
            except Exception as e_season:
                print("Default season notice:", e_season)

        if 'auth_user' in tables:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                admin_user = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
                admin_pass = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin123456')
                admin_email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@ott.local')
                if not User.objects.filter(username=admin_user).exists():
                    User.objects.create_superuser(admin_user, admin_email, admin_pass)
                    print(f"Default superuser '{admin_user}' created on Vercel.")
            except Exception as e_user:
                print("Default superuser notice:", e_user)
    except Exception as e:
        print("Vercel setup notice:", e)
