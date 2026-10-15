#!/usr/bin/env bash
# Render build script — chạy mỗi lần deploy
set -o errexit   # thoát ngay nếu có lỗi

# 1. Cài dependencies
pip install -r requirements.txt

# 2. Thu thập static files vào STATIC_ROOT (staticfiles/)
python manage.py collectstatic --no-input

# 3. Chạy migrations
python manage.py migrate
