"""Small offline round-robin coordinator. No Django/database/network required.

python -m matches.tournament --help
Only operators run this on a dedicated worker. Results stay private until exported.
"""
from __future__ import annotations
import argparse
import ast
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

from .game_engine import RULES_VERSION
from .match_manager import MatchManager


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def write_json(path, value):
    """Atomic replacement prevents partial result files after interruption."""
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def engine_hash():
    root = Path(__file__).parent
    return digest(b''.join((root / name).read_bytes() for name in
                          ('game_engine.py', 'bot_runner.py', 'match_manager.py', 'tournament.py', 'judge_worker.py')))


def schedule(team_ids):
    ids = sorted(team_ids)
    return [{'id': f'g{number:06d}', 'p1': a, 'p2': b}
            for number, (a, b) in enumerate(((a, b) for a in ids for b in ids if a != b), 1)]


def standings(team_ids, games):
    """3/1/0; equal-points mini-table, SB, wins; remaining ties share rank."""
    ids = list(team_ids)
    if len(ids) != len(set(ids)):
        raise ValueError('Trùng mã đội')
    rows = {team: dict(team_id=team, played=0, wins=0, draws=0, losses=0,
                      points=0, head_to_head=0, sb_twice=0) for team in ids}
    scored, seen = [], set()
    for game in games:
        if game['id'] in seen:
            raise ValueError('Trùng mã ván; không được tính điểm hai lần')
        seen.add(game['id'])
        a, b, outcome = game['p1'], game['p2'], game['result']
        if a not in rows or b not in rows or a == b:
            raise ValueError('Đội thi không hợp lệ')
        if outcome == 'error':
            continue
        if outcome not in ('win', 'forfeit', 'draw'):
            raise ValueError('Kết quả không hợp lệ')
        winner = game.get('winner')
        if (outcome == 'draw' and winner is not None) or (outcome != 'draw' and winner not in ('P1', 'P2')):
            raise ValueError('Winner không khớp kết quả')
        points = (1, 1) if outcome == 'draw' else ((3, 0) if winner == 'P1' else (0, 3))
        for team, point in zip((a, b), points):
            row = rows[team]
            row['played'] += 1
            row['points'] += point
            row['wins' if point == 3 else 'draws' if point == 1 else 'losses'] += 1
        scored.append((a, b, points))
    for a, b, points in scored:
        for team, opponent, point in ((a, b, points[0]), (b, a, points[1])):
            if rows[team]['points'] == rows[opponent]['points']:
                rows[team]['head_to_head'] += point
            rows[team]['sb_twice'] += rows[opponent]['points'] * (2 if point == 3 else 1 if point == 1 else 0)
    def key(row):
        return tuple(row[k] for k in ('points', 'head_to_head', 'sb_twice', 'wins'))
    ordered = sorted(rows.values(), key=lambda row: (*(-x for x in key(row)), row['team_id']))
    last, rank = None, 0
    for position, row in enumerate(ordered, 1):
        current = key(row)
        if current != last:
            rank = position
        row['rank'], row['sonneborn_berger'] = rank, row.pop('sb_twice') / 2
        last = current
    return ordered


def freeze(entries_path, destination, image):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('--image phải là image ID sha256 đã build/kiểm tra trên máy chấm')
    entries_path, destination = Path(entries_path), Path(destination)
    entries = json.loads(entries_path.read_text(encoding='utf-8-sig'))
    if not isinstance(entries, list) or not 2 <= len(entries) <= 128:
        raise ValueError('Vòng tròn hỗ trợ 2–128 đội; giải lớn hãy chia bảng trước')
    sources, ids = [], set()
    for entry in entries:
        team = entry['team_id']
        if not isinstance(team, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', team) or team in ids:
            raise ValueError('Mã đội trùng hoặc sai định dạng')
        ids.add(team)
        source = (entries_path.parent / entry['path']).resolve()
        data = source.read_bytes()
        if source.suffix.lower() != '.py' or not 0 < len(data) <= 65536:
            raise ValueError('Bài phải là file .py, không quá 64 KiB')
        ast.parse(data.decode('utf-8-sig'))
        sources.append((team, str(entry.get('name', team)), data))
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'bots').mkdir()
    (destination / 'results').mkdir()
    (destination / 'attempts').mkdir()
    teams = []
    for team, name, data in sources:
        (destination / 'bots' / f'{team}.py').write_bytes(data)
        teams.append({'team_id': team, 'name': name, 'sha256': digest(data)})
    manifest = {'rules_version': RULES_VERSION, 'engine_sha256': engine_hash(),
                'created_at': datetime.now(timezone.utc).isoformat(), 'image': image,
                'max_plies': 300, 'timeout': 5.0, 'teams': teams, 'schedule': schedule(ids)}
    write_json(destination / 'manifest.json', manifest)
    return manifest


def load_frozen(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['rules_version'] != RULES_VERSION or manifest['engine_sha256'] != engine_hash():
        raise ValueError('Engine/runner đã đổi sau khóa bài; khôi phục đúng bản trước khi tiếp tục')
    ids = [team['team_id'] for team in manifest['teams']]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', team) for team in ids):
        raise ValueError('Manifest có mã đội không hợp lệ')
    if manifest['schedule'] != schedule(ids):
        raise ValueError('Lịch đấu không khớp vòng tròn hai lượt')
    if manifest['max_plies'] != 300 or manifest['timeout'] != 5.0:
        raise ValueError('Giới hạn khác luật đã công bố')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', manifest['image']):
        raise ValueError('Image chưa được khóa')
    for team in manifest['teams']:
        if digest((directory / 'bots' / f"{team['team_id']}.py").read_bytes()) != team['sha256']:
            raise ValueError(f"Bài {team['team_id']} đã thay đổi sau khi khóa")
    return manifest, digest(canonical(manifest))


def read_result(directory, game, manifest_hash):
    path = Path(directory) / 'results' / (game['id'] + '.json')
    if not path.exists():
        return None
    result = json.loads(path.read_text(encoding='utf-8'))
    if result['manifest_sha256'] != manifest_hash or result['fixture'] != game or result['replay']['id'] != game['id']:
        raise ValueError('Kết quả không khớp phiên bản/lịch đã khóa')
    if result['replay']['result'] not in ('win', 'forfeit', 'draw'):
        raise ValueError('Kết quả chưa đủ điều kiện tính điểm')
    if digest(canonical(result['replay'])) != result['replay_sha256']:
        raise ValueError('Replay không khớp hash lưu kèm')
    return result


def run(directory):
    directory = Path(directory)
    manifest, manifest_hash = load_frozen(directory)
    lock = directory / '.running'
    # No two coordinators may write the same tournament. An interrupted process
    # leaves the lock as evidence; an operator checks the old process before removal.
    with lock.open('x', encoding='utf-8') as stream:
        stream.write(str(os.getpid()))
    previous_image = os.environ.get('BOT_DOCKER_IMAGE')
    try:
        os.environ['BOT_DOCKER_IMAGE'] = manifest['image']
        for game in manifest['schedule']:
            if read_result(directory, game, manifest_hash):
                continue
            replay = MatchManager().run(
                directory / 'bots' / (game['p1'] + '.py'),
                directory / 'bots' / (game['p2'] + '.py'),
                max_plies=manifest['max_plies'], timeout=manifest['timeout'], match_id=game['id'],
            )
            record = {'manifest_sha256': manifest_hash, 'fixture': game,
                      'replay': replay, 'replay_sha256': digest(canonical(replay)),
                      'finished_at': datetime.now(timezone.utc).isoformat()}
            if replay['result'] == 'error':
                write_json(directory / 'attempts' / (game['id'] + '-' + uuid.uuid4().hex + '.json'), record)
                raise RuntimeError('Dừng vì lỗi hạ tầng/khởi tạo; chưa tính điểm ván này. Sửa lỗi rồi chạy lại.')
            write_json(directory / 'results' / (game['id'] + '.json'), record)
            print(f"{game['id']}: {replay['result']} {replay['winner'] or ''}", flush=True)
    finally:
        if previous_image is None:
            os.environ.pop('BOT_DOCKER_IMAGE', None)
        else:
            os.environ['BOT_DOCKER_IMAGE'] = previous_image
        lock.unlink()


def rank(directory, provisional=False):
    manifest, manifest_hash = load_frozen(directory)
    games = []
    for fixture in manifest['schedule']:
        result = read_result(directory, fixture, manifest_hash)
        if result:
            games.append({**fixture, 'result': result['replay']['result'], 'winner': result['replay']['winner']})
    pending = len(manifest['schedule']) - len(games)
    if pending and not provisional:
        raise ValueError(f'Còn {pending} ván chưa có kết quả; chưa xuất bảng cuối cùng')
    table = standings([team['team_id'] for team in manifest['teams']], games)
    names = {team['team_id']: team['name'] for team in manifest['teams']}
    for row in table:
        row['name'] = names[row['team_id']]
    return {'rules_version': RULES_VERSION, 'manifest_sha256': manifest_hash,
            'provisional': bool(pending), 'pending_games': pending, 'standings': table}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='K71: khóa bài, chạy vòng tròn hai lượt, xuất xếp hạng local')
    sub = parser.add_subparsers(dest='action', required=True)
    prepare = sub.add_parser('freeze')
    prepare.add_argument('entries')
    prepare.add_argument('directory')
    prepare.add_argument('--image', required=True)
    execute = sub.add_parser('run')
    execute.add_argument('directory')
    ranking = sub.add_parser('rank')
    ranking.add_argument('directory')
    ranking.add_argument('--provisional', action='store_true')
    ranking.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'freeze':
            manifest = freeze(args.entries, args.directory, args.image)
            print(f"Đã khóa {len(manifest['teams'])} đội, {len(manifest['schedule'])} ván. Sao lưu toàn bộ thư mục.")
        elif args.action == 'run':
            run(args.directory)
        else:
            output = Path(args.output).resolve()
            if output.exists():
                raise ValueError('File xuất đã tồn tại; chọn tên mới để giữ bản công bố cũ')
            if output.is_relative_to(Path(args.directory).resolve()):
                raise ValueError('Xuất bảng xếp hạng ra ngoài thư mục giải đã khóa')
            write_json(output, rank(args.directory, args.provisional))
    except (ValueError, RuntimeError, OSError, KeyError, SyntaxError) as exc:
        parser.exit(1, f'Lỗi: {exc}\n')


if __name__ == '__main__':
    main()
