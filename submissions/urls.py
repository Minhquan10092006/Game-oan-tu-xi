from django.urls import path
from . import views

urlpatterns = [
    path('', views.SubmissionListCreateView.as_view(), name='submission-list-create'),
    path('<int:pk>/', views.SubmissionDetailView.as_view(), name='submission-detail'),
    path('<int:pk>/result/', views.submission_result_view, name='submission-result'),
]
