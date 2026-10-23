from django.urls import path
from . import competition_views as views

urlpatterns = [
    path('me/', views.my_competition_state),
    path('email/', views.save_contact_email),
    path('seasons/<int:season_id>/individual/', views.register_individual),
    path('seasons/<int:season_id>/teams/', views.create_team),
    path('teams/join/', views.join_team),
    path('teams/<int:team_id>/rotate-code/', views.rotate_team_code),
]
