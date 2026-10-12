from django.urls import path
from . import views

urlpatterns = [
    path('status/', views.judge_status_view, name='judge-status'),
]
