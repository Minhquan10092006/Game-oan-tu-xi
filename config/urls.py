"""
URL configuration cho toàn bộ project.
"""
from django.contrib import admin
from django.urls import include, path
from web.views import rooms_api

urlpatterns = [
    path('', include('web.urls')),
    path('api/rooms/', rooms_api, name='rooms-api'),
    path('api/matches/', include('matches.urls')),
    path('api/submissions/', include('submissions.urls')),
]
