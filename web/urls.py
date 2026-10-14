from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('battlecode/', views.battlecode_demo, name='battlecode-demo'),
    path('ai/', views.ai_judge, name='ai-judge'),
    path('ai-battle/', views.ai_battle_view, name='ai-battle'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('ranking/', views.ranking_view, name='ranking'),
    path('api/rooms/', views.rooms_api, name='rooms-api'),
]
