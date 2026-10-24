from django.urls import path
from . import competition_views as views
from . import operations_views as operations

urlpatterns = [
    path('seasons/create/', operations.create_season),
    path('seasons/<int:season_id>/overview/', operations.overview),
    path('seasons/<int:season_id>/fixtures/', operations.fixtures),
    path('seasons/<int:season_id>/standings/', operations.standings),
    path('seasons/<int:season_id>/operate/', operations.operate),
    path('seasons/<int:season_id>/appeals/', views.retired_feature),
    path('seasons/<int:season_id>/roster/', operations.roster),
    path('seasons/<int:season_id>/waitlist/', operations.waitlist),
    path('entries/<int:entry_id>/choose-bot/', operations.choose_bot),
    path('entries/<int:entry_id>/preflight/', operations.preflight),
    path('entries/<int:entry_id>/withdraw/', operations.withdraw),
    path('jobs/<int:job_id>/retry/', operations.retry),
    path('jobs/<int:job_id>/adjudicate/', operations.adjudicate),
    path('jobs/<int:job_id>/replay/', operations.replay),
    path('appeals/<int:appeal_id>/resolve/', views.retired_feature),
    path('verify-email/', views.retired_feature),
    path('profile/', operations.update_profile),
    path('workers/<str:action>/', operations.worker_api),
    path('me/', views.my_competition_state),
    path('email/', views.retired_feature),
    path('email/check/', views.retired_feature),
    path('teams/<int:team_id>/email/', views.retired_feature),
    path('seasons/<int:season_id>/register/', views.register_representative),
    path('seasons/<int:season_id>/individual/', views.retired_feature),
    path('seasons/<int:season_id>/teams/', views.retired_feature),
    path('teams/join/', views.retired_feature),
    path('teams/<int:team_id>/rotate-code/', views.retired_feature),
]
