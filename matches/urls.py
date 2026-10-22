from django.urls import path
from . import demo_views

urlpatterns = [
    path('sample/', demo_views.create_sample_match, name='sample-match'),
    path('boards/', demo_views.boards, name='demo-boards'),
    path('demo/', demo_views.create_demo_match, name='demo-match-create'),
    path('demo/<str:match_id>/', demo_views.demo_match_detail, name='demo-match-detail'),
    path('demo/<str:match_id>/state/', demo_views.demo_match_state, name='demo-match-state'),
    # Approved bots
    path('approved-bots/', demo_views.approved_bots, name='approved-bots'),
    path('demo-approved/', demo_views.run_approved_bot_match, name='demo-approved-match'),
]
