from django.urls import path
from . import api_views

urlpatterns = [
    path('', api_views.ranking_api, name='ranking-api'),
]
