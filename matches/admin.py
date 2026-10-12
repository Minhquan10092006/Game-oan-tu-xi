from django.contrib import admin
from .models import Match, MatchMove


class MatchMoveInline(admin.TabularInline):
    model = MatchMove
    extra = 0
    readonly_fields = ['player', 'turn_number', 'from_row', 'from_col',
                       'to_row', 'to_col', 'piece_type', 'is_capture', 'created_at']


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'player1_name', 'player2_name', 'status', 'winner', 'created_at']
    list_filter = ['status']
    inlines = [MatchMoveInline]


@admin.register(MatchMove)
class MatchMoveAdmin(admin.ModelAdmin):
    list_display = ['id', 'match', 'player', 'turn_number',
                    'from_row', 'from_col', 'to_row', 'to_col', 'is_capture']
