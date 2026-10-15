#!/usr/bin/env bash
# Render build script — chạy mỗi lần deploy
set -o errexit   # thoát ngay nếu có lỗi

# 1. Cài dependencies
pip install -r requirements.txt

# 2. Thu thập static files vào STATIC_ROOT (staticfiles/)
python manage.py collectstatic --no-input

# 3. Chạy migrations
python manage.py migrate

# 4. Tạo superuser từ biến môi trường nếu chưa có
python manage.py shell -c "
from django.contrib.auth.models import User
import os
u = os.environ.get('DJANGO_SUPERUSER_USERNAME', '')
p = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
e = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
if u and p and not User.objects.filter(username=u).exists():
    User.objects.create_superuser(u, e, p)
    print('Superuser created:', u)
else:
    print('Superuser skipped (already exists or env vars not set)')
"
