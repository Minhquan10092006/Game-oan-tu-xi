from django.urls import path
from . import demo_views

urlpatterns = [
    path('boards/', demo_views.boards, name='demo-boards'),
    path('demo/', demo_views.create_demo_match, name='demo-match-create'),
    path('demo/<str:match_id>/', demo_views.demo_match_detail, name='demo-match-detail'),
    path('demo/<str:match_id>/state/', demo_views.demo_match_state, name='demo-match-state'),
]
