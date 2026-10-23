from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('play/', views.play, name='play'),
    path('login/', views.account, name='login'),
    path('register/', views.account, {'mode': 'register'}, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('battlecode/', views.battlecode_demo, name='battlecode'),
    path('history/', views.match_history, name='history'),
    path('history/<str:match_id>/', views.match_detail, name='match-detail'),
    path('season-admin/', views.season_admin, name='season-admin'),
    path('season-admin/create/', views.season_create, name='season-create'),
    path('season-admin/<int:pk>/toggle/', views.season_toggle, name='season-toggle'),
    path('season-admin/<int:pk>/delete/', views.season_delete, name='season-delete'),
    path('season-admin/<int:pk>/draw/', views.season_draw, name='season-draw'),
    path('season-admin/<int:pk>/email/', views.season_email, name='season-email'),
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
]
