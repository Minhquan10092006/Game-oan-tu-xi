"""
URL configuration cho toàn bộ project.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # Game frontend
    path('', include('web.urls')),
    # REST API
    path('api/submissions/', include('submissions.urls')),
    path('api/matches/', include('matches.urls')),
    path('api/judge/', include('judge.urls')),
    path('api/ranking/', include('web.api_urls')),
]
