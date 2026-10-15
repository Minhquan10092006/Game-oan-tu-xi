from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('logout/', views.logout_view, name='logout'),
    path('battlecode/', views.battlecode_demo, name='battlecode'),
    path('history/', views.match_history, name='history'),
    path('history/<str:match_id>/', views.match_detail, name='match-detail'),
    path('season-admin/', views.season_admin, name='season-admin'),
    path('season-admin/create/', views.season_create, name='season-create'),
    path('season-admin/<int:pk>/toggle/', views.season_toggle, name='season-toggle'),
    path('season-admin/<int:pk>/delete/', views.season_delete, name='season-delete'),
    path('ranking/', views.ranking_view, name='ranking'),
    path('ai/', views.ai_submit, name='ai-submit'),
    path('ai-battle/', views.ai_battle, name='ai-battle'),
    # Admin: xem source code một submission (JSON)
    path('admin/submission/<int:pk>/code/', views.admin_submission_code, name='admin-sub-code'),
    # Admin: trang duyệt code cộng đồng (HTML)
    path('admin/code-review/', views.admin_code_review, name='admin-code-review'),
]
