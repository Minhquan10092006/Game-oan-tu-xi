#!/usr/bin/env bash
# Vercel Build Script — chạy tự động khi deploy trên Vercel
set -o errexit

echo "==> Cài đặt dependencies..."
python3 -m pip install -r requirements.txt

echo "==> Thu thập static files (collectstatic)..."
python3 manage.py collectstatic --no-input --clear

echo "==> Build hoàn tất cho Vercel!"

