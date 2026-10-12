"""
matches/serializers.py
"""
from rest_framework import serializers
from .models import Match, MatchMove


class MatchMoveSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchMove
        fields = [
            'id', 'player', 'turn_number',
            'from_row', 'from_col', 'to_row', 'to_col',
            'piece_type', 'is_capture', 'captured_type',
            'created_at',
        ]


class MatchCreateSerializer(serializers.ModelSerializer):
    """Tạo trận đấu mới."""

    ai1_id = serializers.IntegerField(required=False, allow_null=True)
    ai2_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = Match
        fields = ['player1_name', 'player2_name', 'ai1_id', 'ai2_id', 'max_turns']

    def validate(self, data):
        from submissions.models import Submission
        ai1_id = data.get('ai1_id')
        ai2_id = data.get('ai2_id')

        if ai1_id:
            try:
                ai1 = Submission.objects.get(pk=ai1_id, status='completed')
                data['ai1'] = ai1
            except Submission.DoesNotExist:
                raise serializers.ValidationError(
                    {'ai1_id': 'Bài nộp AI 1 không tồn tại hoặc chưa hoàn thành chấm.'}
                )
        if ai2_id:
            try:
                ai2 = Submission.objects.get(pk=ai2_id, status='completed')
                data['ai2'] = ai2
            except Submission.DoesNotExist:
                raise serializers.ValidationError(
                    {'ai2_id': 'Bài nộp AI 2 không tồn tại hoặc chưa hoàn thành chấm.'}
                )
        return data

    def create(self, validated_data):
        from matches.engine import GameState
        validated_data.pop('ai1_id', None)
        validated_data.pop('ai2_id', None)
        gs = GameState()
        match = Match.objects.create(
            board_state=gs.to_dict(),
            status='playing',
            **validated_data,
        )
        return match


class MatchDetailSerializer(serializers.ModelSerializer):
    moves = MatchMoveSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        fields = [
            'id', 'player1_name', 'player2_name',
            'ai1', 'ai2',
            'status', 'board_state',
            'current_player', 'turn_number',
            'winner', 'win_reason',
            'max_turns',
            'created_at', 'updated_at', 'finished_at',
            'moves',
        ]
        read_only_fields = fields


class AIMoveRequestSerializer(serializers.Serializer):
    """Request body cho /api/matches/{id}/ai-move/."""
    player = serializers.IntegerField(min_value=1, max_value=2)
    submission_id = serializers.IntegerField(required=False, allow_null=True)
