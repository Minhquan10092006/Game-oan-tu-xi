from django.urls import path
from . import views

urlpatterns = [
    path('', views.MatchListCreateView.as_view(), name='match-list-create'),
    path('<int:pk>/', views.MatchDetailView.as_view(), name='match-detail'),
    path('<int:pk>/ai-move/', views.ai_move_view, name='match-ai-move'),
]
