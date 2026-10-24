"""submissions/urls.py — routes cho submission API."""
from django.urls import path
from . import views

urlpatterns = [
    path('session/', views.submission_session, name='submission-session'),
    # ── User endpoints ─────────────────────────────────────────────
    path('', views.SubmissionListCreateView.as_view(), name='submission-list-create'),
    path('approved/', views.approved_bots_list, name='submission-approved'),
    path('<int:pk>/', views.SubmissionDetailView.as_view(), name='submission-detail'),

    # ── Admin endpoints ────────────────────────────────────────────
    # Danh sách tất cả (có thể filter ?status=pending|approved|rejected)
    path('admin/list/', views.admin_submission_list, name='admin-submission-list'),
    # Duyệt / từ chối / xoá từng bài
    path('admin/<int:pk>/approve/', views.admin_approve_submission, name='admin-sub-approve'),
    path('admin/<int:pk>/reject/', views.admin_reject_submission, name='admin-sub-reject'),
    path('admin/<int:pk>/delete/', views.admin_delete_submission, name='admin-sub-delete'),
]
