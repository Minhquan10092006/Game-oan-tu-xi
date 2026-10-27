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


@api_view(['POST'])
@permission_classes([AllowAny])
def solo_match_finish_api(request):
    """
    POST /api/solo/match-finish/
    Nhận kết quả trận đấu từ chế độ Solo/Máy. Cập nhật ELO cho user nếu đã đăng nhập.
    """
    if not request.user.is_authenticated:
        return Response({
            'ok': True,
            'is_guest': True,
            'message': 'Đăng nhập để tích lũy điểm ELO vào Bảng xếp hạng.',
            'elo': 1200,
            'delta': 0,
        })

    try:
        winner = int(request.data.get('winner', 0))
    except (ValueError, TypeError):
        winner = 0

    # Trong chế độ Solo/Chơi cùng máy: Player 1 là user, Player 2 là máy/đối thủ
    if winner == 1:
        won = True
    elif winner == 2:
        won = False
    else:
        won = None

    from .models import update_user_elo_solo
    profile, delta, old_elo, new_elo = update_user_elo_solo(request.user, won)

    return Response({
        'ok': True,
        'is_guest': False,
        'username': request.user.username,
        'won': won,
        'delta': delta,
        'old_elo': old_elo,
        'new_elo': new_elo,
        'wins': profile.wins,
        'losses': profile.losses,
        'draws': profile.draws,
        'win_rate': profile.win_rate,
        'message': f"{'+' if delta > 0 else ''}{delta} ELO" if delta != 0 else "Hòa - Giữ nguyên ELO",
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def user_profile_api(request):
    """
    GET /api/user-profile/
    Trả thông tin ELO và kết quả thi đấu của user hiện tại.
    """
    if not request.user.is_authenticated:
        return Response({
            'authenticated': False,
            'elo': 1200,
            'wins': 0,
            'losses': 0,
            'draws': 0,
            'win_rate': 0.0,
            'total_games': 0,
        })

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return Response({
        'authenticated': True,
        'username': request.user.username,
        'elo': profile.elo,
        'wins': profile.wins,
        'losses': profile.losses,
        'draws': profile.draws,
        'win_rate': profile.win_rate,
        'total_games': profile.total_games,
    })
