"""
matches/middleware.py
---------------------
Rate limiting middleware đơn giản cho API.
"""
import logging
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


class APIRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Giới hạn: (max_requests, window_seconds)
        self.limits = {
            'default': (100, 60),           # 100 req/phút
            '/api/matches/': (30, 60),      # 30 req/phút cho tạo trận
            '/api/matches/ai-battle/start/': (10, 60),  # 10 req/phút cho start battle
            '/api/submissions/': (20, 60),  # 20 req/phút cho nộp bài
        }

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        ip = self._get_client_ip(request)
        path = request.path

        # Tìm limit phù hợp (ưu tiên exact match)
        limit, window = self.limits.get(path, self.limits['default'])
        key = f'ratelimit:{ip}:{path}'

        current = cache.get(key, 0)
        if current >= limit:
            logger.warning(f'Rate limit exceeded: {ip} -> {path} ({current}/{limit})')
            return JsonResponse({
                'error': True,
                'message': 'Quá nhiều yêu cầu. Vui lòng chờ một chút.',
                'retry_after': window
            }, status=429)

        # Atomic increment
        if current == 0:
            cache.add(key, 0, window)
        cache.incr(key)

        response = self.get_response(request)
        # Thêm headers cho client
        response['X-RateLimit-Limit'] = str(limit)
        response['X-RateLimit-Remaining'] = str(max(0, limit - current - 1))
        response['X-RateLimit-Reset'] = str(window)
        return response

    def _get_client_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')