"""
web/api_views.py
----------------
GET /api/ranking/ — bảng xếp hạng ELO, công khai.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import UserProfile


@api_view(['GET'])
@permission_classes([AllowAny])
def ranking_api(request):
    """
    Trả top 50 user theo ELO giảm dần.
    Công khai, không cần đăng nhập.
    """
    top = (
        UserProfile.objects
        .select_related('user')
        .order_by('-elo')[:50]
    )
    data = []
    for rank, profile in enumerate(top, start=1):
        data.append({
            'rank': rank,
            'username': profile.user.username,
            'elo': profile.elo,
            'wins': profile.wins,
            'losses': profile.losses,
            'draws': profile.draws,
            'total_games': profile.total_games,
            'win_rate': profile.win_rate,
        })
    return Response(data)
