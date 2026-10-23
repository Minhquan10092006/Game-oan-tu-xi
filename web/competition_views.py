"""Season entry APIs. They store identities only; they never run or fetch bot code."""
from __future__ import annotations

import hashlib
import re
import secrets
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import (
    CompetitionEntry, Season, Team, TeamMembership, TournamentFixture,
    TournamentRound,
)
from .tournament import group_standings


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode('ascii', errors='ignore')).hexdigest()


def _new_join_code() -> str:
    return 'K71-' + secrets.token_hex(10).upper()


def _registration_open(season: Season) -> bool:
    return (
        season.is_active and not season.drawn_at
        and (not season.registration_deadline or timezone.now() <= season.registration_deadline)
    )


def _entry_payload(entry: CompetitionEntry) -> dict:
    return {
        'id': entry.id, 'season_id': entry.season_id, 'display_name': entry.display_name,
        'kind': 'team' if entry.team_id else 'individual', 'status': entry.status,
    }


def _fixture_slot_name(fixture: TournamentFixture, slot: str) -> str:
    entry = getattr(fixture, f'{slot}_id')
    if entry:
        return getattr(fixture, slot).display_name
    group = getattr(fixture, f'source_group{slot[-1]}')
    rank = getattr(fixture, f'source_rank{slot[-1]}')
    if group and rank:
        return f'{group.code} · Hạng {rank}'
    previous = fixture.incoming_winners.order_by('match_number').first()
    if previous:
        return f'Thắng trận {previous.match_number}'
    return 'Chờ kết quả'


def _fixture_payload(fixture: TournamentFixture) -> dict:
    return {
        'id': fixture.pk,
        'match_number': fixture.match_number,
        'leg': fixture.leg,
        'entry1': _fixture_slot_name(fixture, 'entry1'),
        'entry2': _fixture_slot_name(fixture, 'entry2'),
        'result': fixture.result,
        'winner': fixture.winner.display_name if fixture.winner_id else '',
    }


def _season_tournament_payload(season: Season) -> dict:
    rounds = list(season.rounds.prefetch_related('groups__entries').all())
    groups = []
    bracket = []
    third_place = []
    for tournament_round in rounds:
        if tournament_round.stage == 'group':
            for group in tournament_round.groups.all():
                groups.append({
                    'code': group.code,
                    'standings': [{
                        'rank': row['rank'],
                        'name': row['entry'].display_name,
                        'played': row['played'],
                        'wins': row['wins'],
                        'draws': row['draws'],
                        'losses': row['losses'],
                        'points': row['points'],
                    } for row in group_standings(group)],
                    'fixtures': [
                        _fixture_payload(fixture)
                        for fixture in group.fixtures.select_related(
                            'entry1', 'entry2', 'winner',
                            'winner_to', 'winner_to__tournament_round',
                        ).order_by('match_number')
                    ],
                })
        elif tournament_round.stage == 'third_place':
            third_place = [
                _fixture_payload(fixture)
                for fixture in tournament_round.fixtures.select_related(
                    'entry1', 'entry2', 'winner',
                ).prefetch_related('incoming_winners').order_by('match_number')
            ]
        else:
            bracket.append({
                'name': tournament_round.name,
                'stage': tournament_round.stage,
                'fixtures': [
                    _fixture_payload(fixture)
                    for fixture in tournament_round.fixtures.select_related(
                        'entry1', 'entry2', 'winner',
                        'source_group1', 'source_group2',
                    ).prefetch_related('incoming_winners').order_by('match_number')
                ],
            })
    return {
        'drawn': bool(season.drawn_at),
        'drawn_at': season.drawn_at.isoformat() if season.drawn_at else None,
        'draw_seed': season.draw_seed if season.drawn_at else '',
        'groups': groups,
        'bracket': bracket,
        'third_place': third_place,
    }


def _save_contact_email(request, user):
    email = str(request.data.get('contact_email', '')).strip() or user.email.strip()
    if not email:
        return None
    try:
        validate_email(email)
    except ValidationError:
        return None
    if user.email != email:
        user.email = email
        user.save(update_fields=['email'])
    return email


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def save_contact_email(request):
    if request.session.get('is_guest'):
        return Response({'error': 'Tài khoản khách không thể lưu email thành viên.'}, status=403)
    email = _save_contact_email(request, request.user)
    if not email:
        return Response({'error': 'Nhập địa chỉ email hợp lệ để nhận thông báo giải đấu.'}, status=400)
    return Response({'contact_email': email})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_competition_state(request):
    seasons = Season.objects.filter(Q(is_active=True) | Q(drawn_at__isnull=False)).prefetch_related('rounds')
    entries = CompetitionEntry.objects.filter(
        season__in=seasons,
    ).filter(
        # The second filter is intentionally evaluated below for team membership without exposing other teams.
        status__in=['registered', 'locked'],
    )
    mine = []
    for entry in entries.select_related('season', 'team', 'team__captain', 'user'):
        is_member = entry.team_id and TeamMembership.objects.filter(team=entry.team, user=request.user).exists()
        if entry.user_id == request.user.id or is_member:
            data = _entry_payload(entry)
            data['is_captain'] = bool(entry.team_id and entry.team.captain_id == request.user.id)
            if entry.team_id:
                data['member_count'] = entry.team.memberships.count()
            mine.append(data)
    return Response({'entries': mine, 'seasons': [
        {'id': season.id, 'name': season.name, 'entry_mode': season.entry_mode,
         'registration_open': _registration_open(season),
         **_season_tournament_payload(season),
         'rounds': [{'name': r.name, 'stage': r.stage, 'status': r.status, 'order': r.order}
                    for r in season.rounds.all()]}
        for season in seasons
    ], 'contact_email': request.user.email})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def register_individual(request, season_id):
    if request.session.get('is_guest'):
        return Response({'error': 'Tài khoản khách không thể đăng ký giải.'}, status=403)
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        season = Season.objects.select_for_update().get(pk=season_id)
        if not _registration_open(season) or season.entry_mode == 'team':
            return Response({'error': 'Mùa giải hiện không nhận đăng ký cá nhân.'}, status=409)
        if TeamMembership.objects.filter(user=user, team__season=season).exists():
            return Response({'error': 'Bạn đã thuộc một đội trong mùa này.'}, status=409)
        if not _save_contact_email(request, user):
            return Response({'error': 'Nhập địa chỉ email hợp lệ để nhận thông báo giải đấu.'}, status=400)
        entry, created = CompetitionEntry.objects.get_or_create(
            season=season, user=user, defaults={'display_name': user.username},
        )
    return Response({**_entry_payload(entry), 'created': created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_team(request, season_id):
    if request.session.get('is_guest'):
        return Response({'error': 'Tài khoản khách không thể lập đội.'}, status=403)
    name = str(request.data.get('name', '')).strip()
    if not 3 <= len(name) <= 80:
        return Response({'error': 'Tên đội cần từ 3 đến 80 ký tự.'}, status=400)
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        season = Season.objects.select_for_update().get(pk=season_id)
        if not _registration_open(season) or season.entry_mode == 'individual':
            return Response({'error': 'Mùa giải hiện không nhận đăng ký đội.'}, status=409)
        if not _save_contact_email(request, user):
            return Response({'error': 'Nhập địa chỉ email hợp lệ để nhận thông báo giải đấu.'}, status=400)
        if TeamMembership.objects.filter(user=user, team__season=season).exists() or CompetitionEntry.objects.filter(season=season, user=user).exists():
            return Response({'error': 'Bạn đã có mục dự thi trong mùa này.'}, status=409)
        for _ in range(3):
            code = _new_join_code()
            try:
                team = Team.objects.create(season=season, name=name, captain=user, join_code_hash=_code_hash(code))
                break
            except IntegrityError:
                if Team.objects.filter(season=season, name=name).exists():
                    return Response({'error': 'Tên đội đã tồn tại trong mùa giải.'}, status=409)
        else:
            return Response({'error': 'Không tạo được mã đội; thử lại.'}, status=503)
        TeamMembership.objects.create(team=team, user=user)
        entry = CompetitionEntry.objects.create(season=season, team=team, display_name=team.name)
    return Response({**_entry_payload(entry), 'join_code': code}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def join_team(request):
    if request.session.get('is_guest'):
        return Response({'error': 'Tài khoản khách không thể vào đội.'}, status=403)
    code = str(request.data.get('join_code', '')).strip().upper()
    if not re.fullmatch(r'K71-[0-9A-F]{20}', code):
        return Response({'error': 'Mã đội không hợp lệ.'}, status=400)
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        try:
            team = Team.objects.select_for_update().select_related('season').get(join_code_hash=_code_hash(code))
        except Team.DoesNotExist:
            return Response({'error': 'Mã đội không hợp lệ.'}, status=404)
        if not _registration_open(team.season) or team.is_locked:
            return Response({'error': 'Đội không còn nhận thành viên.'}, status=409)
        if TeamMembership.objects.filter(user=user, team__season=team.season).exists() or CompetitionEntry.objects.filter(season=team.season, user=user).exists():
            return Response({'error': 'Bạn đã có mục dự thi trong mùa này.'}, status=409)
        if team.memberships.count() >= team.season.max_team_size:
            return Response({'error': 'Đội đã đủ thành viên.'}, status=409)
        if not _save_contact_email(request, user):
            return Response({'error': 'Nhập địa chỉ email hợp lệ để nhận thông báo giải đấu.'}, status=400)
        TeamMembership.objects.create(team=team, user=user)
    return Response({'team_name': team.name, 'season_id': team.season_id}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def rotate_team_code(request, team_id):
    with transaction.atomic():
        team = Team.objects.select_for_update().select_related('season').get(pk=team_id)
        if team.captain_id != request.user.id:
            return Response({'error': 'Chỉ đội trưởng được đổi mã đội.'}, status=403)
        if team.is_locked or not _registration_open(team.season):
            return Response({'error': 'Đội không thể đổi mã ở thời điểm này.'}, status=409)
        code = _new_join_code()
        team.join_code_hash = _code_hash(code)
        team.save(update_fields=['join_code_hash'])
    return Response({'join_code': code})
