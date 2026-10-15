"""
judge/views.py
--------------
Endpoint kiểm tra trạng thái Judge0 instance.
"""
import logging

from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from judge.client import get_client, Judge0Error, Judge0Unavailable

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([permissions.IsAdminUser])
def judge_status_view(request):
    """
    GET /api/judge/status/
    Chỉ admin mới được xem. Kiểm tra Judge0 instance còn hoạt động không.
    Không trả API key về client.
    """
    from django.conf import settings
    client = get_client()

    try:
        languages = client.get_languages()
        python3_id = client.get_python3_language_id()
        return Response({
            'available': True,
            'base_url': settings.JUDGE0_BASE_URL,
            'python3_language_id': python3_id,
            'total_languages': len(languages),
        })
    except Judge0Unavailable as e:
        return Response({
            'available': False,
            'base_url': settings.JUDGE0_BASE_URL,
            'error': str(e),
        }, status=503)
    except Judge0Error as e:
        return Response({
            'available': False,
            'base_url': settings.JUDGE0_BASE_URL,
            'error': str(e),
        }, status=500)
