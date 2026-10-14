from django.urls import path
from . import views
from . import demo_views

urlpatterns = [
    path('boards/', demo_views.boards, name='demo-boards'),
    path('demo/', demo_views.create_demo_match, name='demo-match-create'),
    path('demo/<str:match_id>/', demo_views.demo_match_detail, name='demo-match-detail'),
    path('demo/<str:match_id>/state/', demo_views.demo_match_state, name='demo-match-state'),
    path('', views.MatchListCreateView.as_view(), name='match-list-create'),
    path('<int:pk>/', views.MatchDetailView.as_view(), name='match-detail'),
    path('<int:pk>/ai-move/', views.ai_move_view, name='match-ai-move'),
    path('<int:pk>/battle/', views.ai_battle_status_view, name='match-battle-status'),
    path('ai-battle/start/', views.ai_battle_start_view, name='ai-battle-start'),
]
