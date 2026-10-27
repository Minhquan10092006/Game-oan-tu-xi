"""Representative-only registration. Team, contact-email and appeal routes are retired."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import CompetitionEntry, Season, TournamentFixture
from .tournament import group_standings
from .tournament_ops import can_operate, participant_count, audit


def _registration_open(season):
    return (season.is_active and not season.drawn_at and season.phase in ('registration', 'submission')
            and (not season.registration_deadline or timezone.now() <= season.registration_deadline))


def _capacity_error(season, user):
    if participant_count(season) >= min(season.max_participants, 4000):
        return 'Giải đã đủ tài khoản đại diện; bạn có thể vào danh sách chờ.'
    return None


def _entry_payload(entry):
    return {'id': entry.pk, 'season_id': entry.season_id, 'display_name': entry.display_name, 'status': entry.status}


def _entry_position(entry):
    """Resolve the signed-in representative by ID, including large tournaments."""
    from django.db.models import Q
    group = entry.groups.filter(tournament_round__season_id=entry.season_id).prefetch_related('entries', 'fixtures').first()
    rows = group_standings(group) if group else []
    mine = next((row for row in rows if row['entry'].pk == entry.pk), None)
    fixtures = TournamentFixture.objects.filter(
        Q(entry1_id=entry.pk) | Q(entry2_id=entry.pk), tournament_round__season_id=entry.season_id,
    ).select_related('entry1', 'entry2', 'winner', 'group', 'tournament_round').order_by('tournament_round__order', 'match_number')
    return {
        'group': group.code if group else None,
        'rank': mine['rank'] if mine else None,
        'points': mine['points'] if mine else 0,
        'played': mine['played'] if mine else 0,
        'standings': [{'entry_id': row['entry'].pk, 'name': row['entry'].display_name,
                       **{key: row[key] for key in ('rank', 'played', 'wins', 'draws', 'losses', 'points')}} for row in rows],
        'fixtures': [{**_fixture_payload(f), 'round': f.tournament_round.name,
                      'group': f.group.code if f.group_id else None} for f in fixtures],
    }


def _fixture_slot_name(fixture: TournamentFixture, slot: str) -> str:
    entry = getattr(fixture, f'{slot}_id')
    if entry:
        return getattr(fixture, slot).display_name
    group = getattr(fixture, f'source_group{slot[-1]}')
    rank = getattr(fixture, f'source_rank{slot[-1]}')
    if group and rank:
        return f'{group.code} · Hạng {rank}'
    previous = fixture.incoming_winners.filter(winner_to_slot=slot).select_related('tournament_round').order_by('match_number').first()
    if previous:
        return f'Thắng {previous.tournament_round.name} · trận {previous.match_number}'
    return 'Chờ kết quả'


def _fixture_payload(fixture: TournamentFixture) -> dict:
    job = getattr(fixture, 'judging_job', None)
    return {
        'id': fixture.pk,
        'match_number': fixture.match_number,
        'leg': fixture.leg,
        'entry1_id': fixture.entry1_id,
        'entry2_id': fixture.entry2_id,
        'winner_id': fixture.winner_id,
        'winner_to_id': fixture.winner_to_id,
        'winner_to_slot': fixture.winner_to_slot,
        'job_id': job.pk if job else None,
        'job_state': job.state if job else None,
        'entry1': _fixture_slot_name(fixture, 'entry1'),
        'entry2': _fixture_slot_name(fixture, 'entry2'),
        'result': fixture.result,
        'winner': fixture.winner.display_name if fixture.winner_id else '',
    }


def _season_tournament_payload(season: Season) -> dict:
    if season.entries.count() > 128:
        # Large tournaments use paginated fixtures instead of rendering 14k games in every browser.
        return {'drawn': bool(season.drawn_at), 'drawn_at': season.drawn_at.isoformat() if season.drawn_at else None,
                'draw_seed': season.draw_seed, 'groups': [], 'bracket': [], 'third_place': [],
                'paginated': True, 'tournament_url': '/tournament/'}
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
                        'entry_id': row['entry'].pk,
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
                            'winner_to', 'winner_to__tournament_round', 'judging_job',
                        ).order_by('match_number')
                    ],
                })
        elif tournament_round.stage == 'third_place':
            third_place = [
                _fixture_payload(fixture)
                for fixture in tournament_round.fixtures.select_related(
                    'entry1', 'entry2', 'winner', 'judging_job',
                ).prefetch_related('incoming_winners').order_by('match_number')
            ]
        else:
            bracket.append({
                'name': tournament_round.name,
                'stage': tournament_round.stage,
                'fixtures': [
                    _fixture_payload(fixture)
                    for fixture in tournament_round.fixtures.select_related(
                        'entry1', 'entry2', 'winner', 'judging_job',
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



@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def season_draw(request, season_id):
    season = get_object_or_404(Season, pk=season_id)
    entry = CompetitionEntry.objects.filter(season=season,user=request.user).exclude(status='withdrawn').first()
    return Response({'season': {'id':season.pk,'name':season.name,'phase':season.phase,**_season_tournament_payload(season)},
                     'entry': {**_entry_payload(entry),'position':_entry_position(entry)} if entry else None})


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_competition_state(request):
    seasons = Season.objects.filter(is_active=True).prefetch_related('rounds')
    entries = CompetitionEntry.objects.filter(season__in=seasons, user=request.user).exclude(status='withdrawn')
    return Response({'entries': [{**_entry_payload(e), 'position': _entry_position(e)} for e in entries], 'seasons': [
        {'id': s.pk, 'name': s.name, 'phase': s.phase, 'registration_open': _registration_open(s),
         'registration_deadline': s.registration_deadline, 'submission_deadline': s.submission_deadline,
         'participants': participant_count(s), 'capacity': min(s.max_participants, 4000),
         'rounds': [{'name': r.name, 'status': r.status, 'stage': r.stage, 'order': r.order} for r in s.rounds.all()],
         **_season_tournament_payload(s)} for s in seasons]})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def register_representative(request, season_id):
    if request.session.get('is_guest') or can_operate(request.user):
        return Response({'error': 'Dùng tài khoản sinh viên đại diện để đăng ký dự thi.'}, status=403)
    with transaction.atomic():
        season = get_object_or_404(Season.objects.select_for_update(), pk=season_id)
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if not _registration_open(season):
            return Response({'error': 'Giải đã hết hạn đăng ký, khóa bài hoặc bốc thăm.'}, status=409)
        existing = CompetitionEntry.objects.filter(season=season, user=user).first()
        if existing and existing.status == 'disqualified':
            return Response({'error': 'Mục dự thi đã bị loại; liên hệ ban tổ chức.'}, status=403)
        if existing and existing.status in ('registered', 'locked'):
            return Response({**_entry_payload(existing), 'created': False})
        error = _capacity_error(season, user)
        if error:
            return Response({'error': error}, status=409)
        name = str(request.data.get('display_name', '')).strip() or user.username
        if len(name) > 120:
            return Response({'error': 'Tên dự thi tối đa 120 ký tự.'}, status=400)
        if existing:
            existing.status, existing.display_name = 'registered', name
            existing.save(update_fields=['status', 'display_name'])
            entry = existing
        else:
            entry = CompetitionEntry.objects.create(season=season, user=user, display_name=name)
        audit(season, user, 'register_representative', entry=entry.pk)
    return Response({**_entry_payload(entry), 'created': True}, status=status.HTTP_201_CREATED)


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def retired_feature(request, **kwargs):
    return Response({'error': 'Chức năng này đã được bỏ. Mỗi nhóm dùng một tài khoản đại diện; xem /tournament/.'}, status=410)
