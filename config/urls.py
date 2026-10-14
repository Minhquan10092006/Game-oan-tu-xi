"""
URL configuration cho toàn bộ project.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Demo tối giản: giao diện upload + API replay. Các route Judge0/ELO cũ không được public.
    path('', include('web.urls')),
    path('api/matches/', include('matches.urls')),
]
