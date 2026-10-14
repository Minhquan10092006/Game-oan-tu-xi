"""
URL configuration cho toàn bộ project.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('', include('web.urls')),
    path('api/matches/', include('matches.urls')),
    path('api/submissions/', include('submissions.urls')),
]
