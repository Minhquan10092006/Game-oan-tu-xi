from django.contrib import admin
from .models import UserProfile, Season, MatchHistory


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'elo', 'wins', 'losses', 'draws', 'updated_at')
    ordering = ('-elo',)
    search_fields = ('user__username',)


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'start_date', 'end_date', 'created_by', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)

    def match_count(self, obj):
        return obj.matches.count()
    match_count.short_description = 'Số trận'


@admin.register(MatchHistory)
class MatchHistoryAdmin(admin.ModelAdmin):
    list_display = ('match_id', 'player', 'season', 'board_preset', 'result', 'total_plies', 'played_at')
    list_filter = ('result', 'board_preset', 'season')
    search_fields = ('match_id', 'player__username')
    readonly_fields = ('match_id', 'played_at', 'replay_data')

    def has_add_permission(self, request):
        return False
