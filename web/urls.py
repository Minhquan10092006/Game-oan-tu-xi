from django.urls import path
from . import views

urlpatterns = [
    path('', views.battlecode_demo, name='battlecode-demo'),
    path('battlecode/', views.battlecode_demo, name='battlecode-demo-alias'),
]
