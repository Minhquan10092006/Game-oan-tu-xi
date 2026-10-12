"""
web/routing.py
==============
WebSocket URL routing cho app web.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/multiplayer/?$', consumers.MultiplayerConsumer.as_asgi()),
]
