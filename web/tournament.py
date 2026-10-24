"""Persistent, reproducible group draws and knockout brackets for web seasons."""
from __future__ import annotations

import hashlib
import itertools
import math
import random
import secrets
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from .models import (
    CompetitionEntry, Season, TournamentFixture, TournamentGroup, TournamentRound,
)

GROUP_SIZE = 4
QUALIFIERS_PER_GROUP = 2
ROUND_LABELS = {
    'round_of_4096': 'Vòng 4096', 'round_of_2048': 'Vòng 2048',
    'round_of_1024': 'Vòng 1024', 'round_of_512': 'Vòng 512',
    'round_of_256': 'Vòng 256', 'round_of_128': 'Vòng 128',
    'round_of_64': 'Vòng 64', 'round_of_32': 'Vòng 32',
    'round_of_16': 'Vòng 16', 'quarterfinal': 'Tứ kết',
    'semifinal': 'Bán kết', 'final': 'Chung kết',
}


class DrawError(ValueError):
    """The season cannot be drawn in its current state."""


def group_code(index: int) -> str:
    """Return spreadsheet-style group labels: A..Z, AA.."""
    label = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _round_stage(size: int) -> str:
    if size == 2:
        return 'final'
    if size == 4:
        return 'semifinal'
    if size == 8:
        return 'quarterfinal'
    if size in (16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
        return f'round_of_{size}'
    raise DrawError('Quy mô nhánh loại trực tiếp vượt giới hạn 4096 suất.')


def _balanced_groups(entries: list[CompetitionEntry], rng: random.Random) -> list[list[CompetitionEntry]]:
    rng.shuffle(entries)
    count = math.ceil(len(entries) / GROUP_SIZE)
    sizes = [len(entries) // count + (index < len(entries) % count) for index in range(count)]
    groups, offset = [], 0
    for size in sizes:
        groups.append(entries[offset:offset + size])
        offset += size
    return groups


def _round_robin_pairs(entries: list[CompetitionEntry]) -> list[tuple[CompetitionEntry, CompetitionEntry]]:
    return list(itertools.combinations(entries, 2))


def _select_byes(slots: list[tuple[TournamentGroup, int]], count: int,
                 rng: random.Random) -> list[tuple[TournamentGroup, int]]:
    if count <= 0:
        return []
    shuffled = slots[:]
    rng.shuffle(shuffled)
    byes = []
    used_groups = set()
    for slot in shuffled:
        if slot[0].pk not in used_groups:
            byes.append(slot)
            used_groups.add(slot[0].pk)
            if len(byes) == count:
                return byes
    byes_set = set(byes)
    remaining = [slot for slot in shuffled if slot not in byes_set]
    rng.shuffle(remaining)
    byes.extend(remaining[:count - len(byes)])
    return byes


def _pair_slots(slots: list[tuple[TournamentGroup, int]], rng: random.Random):
    remaining = defaultdict(list)
    for slot in slots:
        remaining[slot[0].pk].append(slot)
    for group_slots in remaining.values():
        rng.shuffle(group_slots)
    pairs = []
    while sum(map(len, remaining.values())):
        group_ids = [group_id for group_id, group_slots in remaining.items() if group_slots]
        rng.shuffle(group_ids)
        group_ids.sort(key=lambda group_id: len(remaining[group_id]), reverse=True)
        first_group, second_group = group_ids[:2] if len(group_ids) > 1 else (group_ids[0], group_ids[0])
        pairs.append((remaining[first_group].pop(), remaining[second_group].pop()))
    return pairs


def _ensure_draw_rounds(season: Season, knockout_sizes: list[int], has_third_place: bool):
    rounds = list(season.rounds.all())
    if any(item.status != 'planned' for item in rounds):
        raise DrawError('Không thể bốc thăm vì đã có vòng đấu bắt đầu.')
    if TournamentFixture.objects.filter(tournament_round__season=season).exists():
        raise DrawError('Mùa giải đã có lịch đấu; không thể bốc thăm lại.')

    desired = [('group', 'Vòng bảng')]
    for size in knockout_sizes[:-1]:
        stage = _round_stage(size)
        desired.append((stage, ROUND_LABELS.get(stage, f'Vòng {size}')))
    if has_third_place:
        desired.append(('third_place', 'Tranh hạng ba'))
    final_stage = _round_stage(knockout_sizes[-1])
    desired.append((final_stage, ROUND_LABELS.get(final_stage, f'Vòng {knockout_sizes[-1]}')))

    TournamentRound.objects.filter(season=season).delete()
    chosen = TournamentRound.objects.bulk_create([
        TournamentRound(
            season=season, stage=stage, order=order, name=label,
            format_note=(
                'Chia bảng ngẫu nhiên, đá vòng tròn hai lượt; thắng 3, hòa 1, thua 0.'
                if stage == 'group' else ''
            ),
            advance_count=QUALIFIERS_PER_GROUP if stage == 'group' else 0,
        )
        for order, (stage, label) in enumerate(desired, 1)
    ])
    return chosen[0], {item.stage: item for item in chosen}


@transaction.atomic
def draw_season(season_id: int) -> dict:
    """Lock entrants and create a durable group schedule and bracket skeleton."""
    season = Season.objects.select_for_update().get(pk=season_id)
    if season.drawn_at or TournamentGroup.objects.filter(tournament_round__season=season).exists():
        raise DrawError('Mùa giải này đã được bốc thăm; không thể bốc thăm lại.')

    entries = list(
        CompetitionEntry.objects.select_for_update(of=('self',)).filter(
            season=season, status__in=['registered', 'locked'],
        ).select_related('team', 'user').order_by('pk')
    )
    if len(entries) < 2:
        raise DrawError('Cần ít nhất 2 mục dự thi đã đăng ký để bốc thăm.')

    seed = secrets.token_hex(16)
    rng = random.Random(seed)
    drawn_groups = _balanced_groups(entries, rng)
    qualifiers = [(group_index, rank) for group_index in range(len(drawn_groups))
                  for rank in range(1, QUALIFIERS_PER_GROUP + 1)]
    bracket_size = 2 ** math.ceil(math.log2(len(qualifiers)))
    stage_sizes = [bracket_size // (2 ** index) for index in range(int(math.log2(bracket_size)))]
    group_round, stage_rounds = _ensure_draw_rounds(
        season, stage_sizes, has_third_place=bracket_size >= 4,
    )

    groups = []
    match_number = 0
    for index, members in enumerate(drawn_groups, 1):
        group = TournamentGroup.objects.create(
            tournament_round=group_round, code=group_code(index),
            draw_order=index,
        )
        group.entries.set(members)
        groups.append(group)
        for entry1, entry2 in _round_robin_pairs(members):
            match_number += 1
            TournamentFixture.objects.create(
                tournament_round=group_round, group=group,
                match_number=match_number, leg=1, entry1=entry1, entry2=entry2,
            )
            match_number += 1
            TournamentFixture.objects.create(
                tournament_round=group_round, group=group,
                match_number=match_number, leg=2, entry1=entry2, entry2=entry1,
            )

    qualifier_slots = [(groups[group_index], rank) for group_index, rank in qualifiers]
    byes = _select_byes(qualifier_slots, bracket_size - len(qualifier_slots), rng)
    bye_set = set(byes)
    first_round_slots = [slot for slot in qualifier_slots if slot not in bye_set]
    first_round_matches = [
        (slot, None) for slot in byes
    ] + _pair_slots(first_round_slots, rng)
    rng.shuffle(first_round_matches)

    round_fixtures = {}
    first_round = stage_rounds[_round_stage(bracket_size)]
    round_fixtures[first_round.stage] = []
    for index, pair in enumerate(first_round_matches, 1):
        first, second = pair
        if second is not None and rng.choice((True, False)):
            first, second = second, first
        fixture = TournamentFixture.objects.create(
            tournament_round=first_round, match_number=index,
            source_group1=first[0], source_rank1=first[1],
            source_group2=second[0] if second else None,
            source_rank2=second[1] if second else None,
            result='bye' if second is None else 'scheduled',
        )
        round_fixtures[first_round.stage].append(fixture)

    earlier_round = first_round
    for size in stage_sizes[1:]:
        stage = _round_stage(size)
        current_round = stage_rounds[stage]
        round_fixtures[stage] = [
            TournamentFixture.objects.create(
                tournament_round=current_round, match_number=index,
            )
            for index in range(1, size // 2 + 1)
        ]
        previous_fixtures = round_fixtures[earlier_round.stage]
        next_fixtures = round_fixtures[stage]
        for index, fixture in enumerate(previous_fixtures):
            fixture.winner_to = next_fixtures[index // 2]
            fixture.winner_to_slot = 'entry1' if index % 2 == 0 else 'entry2'
            if earlier_round.stage == 'semifinal':
                third_place = stage_rounds['third_place']
                third_fixture = TournamentFixture.objects.get(
                    tournament_round=third_place, match_number=1,
                ) if TournamentFixture.objects.filter(tournament_round=third_place).exists() else None
                if third_fixture is None:
                    third_fixture = TournamentFixture.objects.create(tournament_round=third_place, match_number=1)
                fixture.loser_to = third_fixture
                fixture.loser_to_slot = 'entry1' if index == 0 else 'entry2'
            fixture.save(update_fields=['winner_to', 'winner_to_slot', 'loser_to', 'loser_to_slot'])
        earlier_round = current_round

    if 'third_place' in stage_rounds and not TournamentFixture.objects.filter(
        tournament_round=stage_rounds['third_place'],
    ).exists():
        TournamentFixture.objects.create(
            tournament_round=stage_rounds['third_place'], match_number=1,
        )

    season.draw_seed = seed
    season.drawn_at = timezone.now()
    season.save(update_fields=['draw_seed', 'drawn_at'])
    group_round.status = 'active'
    group_round.save(update_fields=['status'])
    CompetitionEntry.objects.filter(season=season, status='registered').update(status='locked')
    season.teams.update(is_locked=True)
    return {
        'season': season, 'groups': groups, 'entries': len(entries),
        'group_count': len(groups), 'qualifier_count': len(qualifiers),
        'bracket_size': bracket_size, 'bye_count': len(byes),
    }


def group_standings(group: TournamentGroup) -> list[dict]:
    prefetched = getattr(group, '_prefetched_objects_cache', {})
    members = sorted(prefetched['entries'], key=lambda entry: (entry.display_name, entry.pk)) if 'entries' in prefetched else list(group.entries.order_by('display_name', 'pk'))
    stats = {
        entry.pk: {'entry': entry, 'played': 0, 'wins': 0, 'draws': 0, 'losses': 0, 'points': 0}
        for entry in members
    }
    fixtures = list(prefetched['fixtures']) if 'fixtures' in prefetched else list(group.fixtures.all())
    head_to_head = defaultdict(int)
    for fixture in fixtures:
        if fixture.result == 'scheduled' or fixture.entry1_id not in stats or fixture.entry2_id not in stats:
            continue
        first, second = stats[fixture.entry1_id], stats[fixture.entry2_id]
        first['played'] += 1
        second['played'] += 1
        if fixture.result == 'entry1_win':
            first['wins'] += 1
            first['points'] += 3
            second['losses'] += 1
            head_to_head[(fixture.entry1_id, fixture.entry2_id)] += 3
        elif fixture.result == 'entry2_win':
            second['wins'] += 1
            second['points'] += 3
            first['losses'] += 1
            head_to_head[(fixture.entry2_id, fixture.entry1_id)] += 3
        else:
            first['draws'] += 1
            second['draws'] += 1
            first['points'] += 1
            second['points'] += 1
            head_to_head[(fixture.entry1_id, fixture.entry2_id)] += 1
            head_to_head[(fixture.entry2_id, fixture.entry1_id)] += 1

    ordered = list(stats.values())
    ordered.sort(key=lambda row: (row['points'], row['wins']), reverse=True)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and (
            ordered[end]['points'], ordered[end]['wins']
        ) == (ordered[start]['points'], ordered[start]['wins']):
            end += 1
        tied = ordered[start:end]
        if len(tied) > 1:
            tied_ids = {row['entry'].pk for row in tied}
            tied.sort(key=lambda row: (
                sum(points for (winner, opponent), points in head_to_head.items()
                    if winner == row['entry'].pk and opponent in tied_ids),
                hashlib.sha256(
                    f'{group.tournament_round.season.draw_seed}:{group.pk}:{row["entry"].pk}'.encode()
                ).hexdigest(),
            ), reverse=True)
            ordered[start:end] = tied
        start = end
    return [{**row, 'rank': index} for index, row in enumerate(ordered, 1)]


def _set_fixture_entry(fixture: TournamentFixture, slot: str, entry: CompetitionEntry | None):
    setattr(fixture, slot, entry)
    fixture.save(update_fields=[slot])


def _propagate_result(fixture: TournamentFixture):
    if fixture.winner_to_id and fixture.winner_id:
        _set_fixture_entry(fixture.winner_to, fixture.winner_to_slot, fixture.winner)
    if fixture.loser_to_id:
        loser_id = fixture.entry2_id if fixture.winner_id == fixture.entry1_id else fixture.entry1_id
        loser = CompetitionEntry.objects.filter(pk=loser_id).first()
        if loser:
            _set_fixture_entry(fixture.loser_to, fixture.loser_to_slot, loser)


@transaction.atomic
def record_fixture_result(fixture_id: int, result: str):
    season_id = TournamentFixture.objects.values_list('tournament_round__season_id', flat=True).get(pk=fixture_id)
    Season.objects.select_for_update().get(pk=season_id)
    fixture = TournamentFixture.objects.select_for_update(of=('self',)).select_related(
        'entry1', 'entry2', 'tournament_round', 'group',
    ).get(pk=fixture_id)
    if fixture.result != 'scheduled':
        raise DrawError('Kết quả ván này đã được ghi nhận.')
    if result not in {'entry1_win', 'entry2_win', 'draw'}:
        raise DrawError('Kết quả được chọn không hợp lệ.')
    if fixture.entry1_id is None or fixture.entry2_id is None:
        raise DrawError('Chưa xác định đủ hai đơn vị thi đấu cho ván này.')
    if fixture.group_id is None and result == 'draw':
        raise DrawError('Vòng loại trực tiếp không chấp nhận kết quả hòa.')
    if fixture.group_id is not None and fixture.group is not None:
        fixture.result = result
        if result == 'entry1_win':
            fixture.winner = fixture.entry1
        elif result == 'entry2_win':
            fixture.winner = fixture.entry2
        fixture.save(update_fields=['result', 'winner'])
        group_round_fixtures = TournamentFixture.objects.filter(
            tournament_round=fixture.tournament_round, group__isnull=False,
        )
        if group_round_fixtures.exists() and not group_round_fixtures.filter(result='scheduled').exists():
            _seed_knockout_bracket(fixture.tournament_round.season_id)
            fixture.tournament_round.status = 'completed'
            fixture.tournament_round.save(update_fields=['status'])
            first_knockout = TournamentRound.objects.filter(
                season_id=fixture.tournament_round.season_id,
            ).exclude(stage__in=['group', 'third_place']).order_by('order').first()
            if first_knockout:
                first_knockout.status = 'active'
                first_knockout.save(update_fields=['status'])
        return fixture

    fixture.result = result
    fixture.winner = fixture.entry1 if result == 'entry1_win' else fixture.entry2
    fixture.save(update_fields=['result', 'winner'])
    _propagate_result(fixture)
    round_fixtures = TournamentFixture.objects.filter(tournament_round=fixture.tournament_round)
    if not round_fixtures.filter(result='scheduled').exists():
        fixture.tournament_round.status = 'completed'
        fixture.tournament_round.save(update_fields=['status'])
        if fixture.tournament_round.stage == 'semifinal':
            TournamentRound.objects.filter(
                season_id=fixture.tournament_round.season_id,
                stage__in=['third_place', 'final'],
            ).update(status='active')
        elif fixture.tournament_round.stage != 'final':
            next_round = TournamentRound.objects.filter(
                season_id=fixture.tournament_round.season_id,
                order__gt=fixture.tournament_round.order,
            ).exclude(stage='third_place').order_by('order').first()
            if next_round:
                next_round.status = 'active'
                next_round.save(update_fields=['status'])
    return fixture


@transaction.atomic
def _seed_knockout_bracket(season_id: int):
    fixtures = TournamentFixture.objects.select_related(
        'source_group1', 'source_group2', 'tournament_round',
    ).filter(
        tournament_round__season_id=season_id,
        source_group1__isnull=False,
    ).order_by('tournament_round__order', 'match_number')
    standings = {}
    for fixture in fixtures:
        for group, rank in (
            (fixture.source_group1, fixture.source_rank1),
            (fixture.source_group2, fixture.source_rank2),
        ):
            if group and group.pk not in standings:
                standings[group.pk] = group_standings(group)
        if fixture.source_group1:
            first = next((row['entry'] for row in standings[fixture.source_group1_id]
                          if row['rank'] == fixture.source_rank1), None)
            _set_fixture_entry(fixture, 'entry1', first)
        if fixture.source_group2:
            second = next((row['entry'] for row in standings[fixture.source_group2_id]
                           if row['rank'] == fixture.source_rank2), None)
            _set_fixture_entry(fixture, 'entry2', second)
        if fixture.result == 'bye':
            fixture.winner = fixture.entry1 or fixture.entry2
            fixture.save(update_fields=['winner'])
            _propagate_result(fixture)
