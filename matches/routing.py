"""
matches/routing.py
------------------
WebSocket URL routing.
"""
from django.urls import re_path
from .consumers import MatchConsumer

websocket_urlpatterns = [
    re_path(r'ws/match/(?P<match_id>\d+)/$', MatchConsumer.as_asgi()),
]