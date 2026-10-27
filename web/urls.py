from django.urls import path
from . import views
from . import practice_views
from . import api_views
from .operations_views import dashboard, usage_guide
from .competition_views import retired_feature

urlpatterns = [
    path('practice/', practice_views.page, name='practice'),
    path('api/practice/options/', practice_views.options),
    path('api/practice/matches/', practice_views.matches),
    path('api/practice/matches/<int:match_id>/cancel/', practice_views.cancel),
    path('api/practice/matches/<int:match_id>/replay/', practice_views.replay),
    path('submission-sw.js', views.submission_service_worker, name='submission-service-worker'),
    path('ai/offline/', views.submission_offline_shell, name='submission-offline'),
    path('guide/', usage_guide, name='usage-guide'),
    path('tournament/', dashboard, name='tournament-operations'),
    path('', views.index, name='index'),
    path('play/', views.play, name='play'),
    path('login/', views.account, name='login'),
    path('register/', views.account, {'mode': 'register'}, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('battlecode/', views.battlecode_demo, name='battlecode'),
    path('history/', views.match_history, name='history'),
    path('history/<str:match_id>/', views.match_detail, name='match-detail'),
    path('season-admin/', dashboard, name='season-admin'),
    path('season-admin/create/', retired_feature, name='season-create'),
    path('season-admin/<int:pk>/toggle/', views.season_toggle, name='season-toggle'),
    path('season-admin/<int:pk>/delete/', views.season_delete, name='season-delete'),
    path('season-admin/<int:pk>/draw/', retired_feature, name='season-draw'),
    path('season-admin/<int:pk>/email/', retired_feature, name='season-email'),
    path('season-admin/fixtures/<int:pk>/result/', views.tournament_fixture_result, name='fixture-result'),
    path('ranking/', views.ranking_view, name='ranking'),
    path('ai/', views.ai_submit, name='ai-submit'),
    path('competition/', views.competition_hub, name='competition-hub'),
    path('rules/download/', views.rules_markdown_download, name='rules-download'),
    path('ai-battle/', views.ai_battle, name='ai-battle'),
    # Admin: xem source code một submission (JSON)
    path('admin/submission/<int:pk>/code/', views.admin_submission_code, name='admin-sub-code'),
    # Admin: trang duyệt code cộng đồng (HTML)
    path('admin/code-review/', views.admin_code_review, name='admin-code-review'),
    # ELO & Solo match finish API
    path('api/solo/match-finish/', api_views.solo_match_finish_api, name='solo-match-finish'),
    path('api/user-profile/', api_views.user_profile_api, name='user-profile-api'),
]
