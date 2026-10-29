#!/usr/bin/env bash
# Vercel Build Script — chạy tự động khi deploy trên Vercel
set -o errexit

export PIP_BREAK_SYSTEM_PACKAGES=1

echo "==> Cài đặt dependencies..."
if command -v uv &> /dev/null; then
    echo "==> Phát hiện uv, sử dụng uv để cài đặt nhanh..."
    uv pip install --system -r requirements.txt || python3 -m pip install --break-system-packages -r requirements.txt
else
    python3 -m pip install --break-system-packages -r requirements.txt
fi

echo "==> Thu thập static files (collectstatic)..."
python3 manage.py collectstatic --no-input --clear

echo "==> Build hoàn tất cho Vercel!"
