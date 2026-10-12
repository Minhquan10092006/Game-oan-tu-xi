from django.urls import path
from . import views

urlpatterns = [
    path('', views.MatchListCreateView.as_view(), name='match-list-create'),
    path('<int:pk>/', views.MatchDetailView.as_view(), name='match-detail'),
    path('<int:pk>/ai-move/', views.ai_move_view, name='match-ai-move'),
    path('<int:pk>/battle/', views.ai_battle_status_view, name='match-battle-status'),
    path('ai-battle/start/', views.ai_battle_start_view, name='ai-battle-start'),
]
