"""Private practice uses existing worker protocol, without changing engine hashes."""
import hashlib
import json
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone
from matches.practice_bots import BOTS
from matches.tournament import engine_hash
from submissions.models import Submission
from .models import PracticeMatch, JudgeWorker, JudgingJob
from . import tournament_ops as ops


def signature(submission_id, opponent_key, side):
    return hashlib.sha256(json.dumps([submission_id, opponent_key, side]).encode()).hexdigest()


@transaction.atomic
def create(user, request_id, submission_id, opponent_key, side):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    digest = signature(submission_id, opponent_key, side)
    previous = PracticeMatch.objects.filter(user=user, request_id=request_id).first()
    if previous:
        if previous.request_hash != digest:
            raise ValueError('Mã lần tạo trận đã được dùng cho lựa chọn khác.')
        return previous, False
    if side not in ('P1', 'P2'):
        raise ValueError('Chọn bên P1 hoặc P2.')
    if PracticeMatch.objects.filter(user=user, state__in=['queued','running']).exists():
        raise ValueError('Bạn đã có một trận đang chờ hoặc đang chấm. Hãy chờ trận đó hoàn tất.')
    if PracticeMatch.objects.filter(user=user, created_at__date=timezone.localdate()).count() >= settings.PRACTICE_MATCHES_PER_DAY:
        raise ValueError('Đã hết số trận luyện tập trong ngày.')
    own = Submission.objects.filter(pk=submission_id, submitter=user).exclude(review_status='rejected').first()
    if not own:
        raise ValueError('Hãy chọn bài của bạn đã nộp và chưa bị từ chối.')
    opponent = None
    if opponent_key.startswith('sample:'):
        sample = BOTS.get(opponent_key[7:])
        if not sample:
            raise ValueError('Bot mẫu không tồn tại.')
        source, label = sample['source'], sample['name']
    elif opponent_key.startswith('submission:') and opponent_key[11:].isdigit():
        opponent = Submission.objects.filter(pk=int(opponent_key[11:]), review_status='approved').select_related('submitter').first()
        if not opponent:
            raise ValueError('Bot đối thủ chưa được duyệt hoặc không còn khả dụng.')
        source, label = opponent.source_code, f'{opponent.ai_name} v{opponent.version} · {opponent.submitter.username}'
    else:
        raise ValueError('Hãy chọn một bot đối thủ hợp lệ.')
    configured = settings.PRACTICE_DOCKER_IMAGE or settings.TOURNAMENT_DOCKER_IMAGE
    match = PracticeMatch.objects.create(user=user, request_id=request_id, request_hash=digest,
        submission=own, opponent=opponent, own_label=f'{own.ai_name} v{own.version}', opponent_label=label[:220], opponent_key=opponent_key,
        own_source=own.source_code, opponent_source=source, player_side=side, image=configured, engine=engine_hash())
    return match, True


@transaction.atomic
def claim(worker_id, reported_engine):
    worker = JudgeWorker.objects.select_for_update().get(pk=worker_id, enabled=True)
    now = timezone.now()
    if PracticeMatch.objects.filter(worker=worker, state='running', lease_until__gt=now).exists():
        worker.last_seen = now; worker.save(update_fields=['last_seen'])
        if reported_engine != engine_hash():
            raise ValueError('Phiên bản engine trên máy chấm không khớp web.')
        return None
    # The existing coordinator gets first choice: practice never displaces a
    # ready official job. An already-running practice finishes normally.
    official = ops.claim_job(worker_id, reported_engine)
    if official or JudgingJob.objects.filter(worker=worker, state='running', lease_until__gt=now).exists():
        return official
    rows = PracticeMatch.objects.select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
    for expired in rows.filter(state='running', lease_until__lte=now):
        expired.state = 'failed' if expired.attempts >= ops.MAX_ATTEMPTS else 'queued'
        expired.worker = None; expired.lease_token = ''; expired.lease_until = None
        expired.message = 'Máy chấm mất kết nối; đang đợi chấm lại.' if expired.state == 'queued' else 'Máy chấm mất kết nối nhiều lần. Bạn có thể tạo trận mới.'
        expired.save()
    match = rows.filter(state='queued').order_by('created_at','pk').first()
    if not match:
        return None
    if match.engine != reported_engine:
        match.state = 'failed'; match.message = 'Môi trường chấm đã cập nhật. Hãy tạo trận mới.'; match.save()
        return None
    statuses = dict(Submission.objects.filter(pk__in=[match.submission_id,match.opponent_id]).values_list('pk','review_status'))
    if (match.submission_id not in statuses or statuses[match.submission_id] == 'rejected'
            or (match.opponent_key.startswith('submission:') and statuses.get(match.opponent_id) != 'approved')):
        match.state = 'failed'; match.message = 'Một trong hai bot không còn khả dụng. Hãy chọn bot khác.'; match.save()
        return None
    match.state = 'running'; match.worker = worker
    match.lease_token = secrets.token_hex(32); match.lease_until = now + timedelta(seconds=ops.LEASE_SECONDS)
    match.attempts += 1; match.message = ''; match.save()
    sources = [match.own_source,match.opponent_source] if match.player_side == 'P1' else [match.opponent_source,match.own_source]
    return {'id': f'practice-{match.pk}', 'kind':'practice', 'lease_token':match.lease_token,
            'image':match.image, 'engine':match.engine,
            'bots':[{'source':source,'sha256':hashlib.sha256(source.encode()).hexdigest()} for source in sources]}


@transaction.atomic
def update(worker, job_id, token, result=None, *, heartbeat=False):
    JudgeWorker.objects.select_for_update().get(pk=worker.pk, enabled=True)
    try:
        pk = int(str(job_id).removeprefix('practice-'))
    except (ValueError,TypeError):
        raise ValueError('Mã trận luyện tập không hợp lệ.')
    match = PracticeMatch.objects.select_for_update().get(pk=pk)
    if (match.state != 'running' or match.worker_id != worker.pk or not match.lease_until
            or match.lease_until <= timezone.now() or not secrets.compare_digest(match.lease_token,str(token))):
        raise ValueError('Lượt chấm đã hết hạn hoặc không thuộc máy này.')
    if match.engine != engine_hash():
        raise ValueError('Phiên bản máy chấm đã thay đổi.')
    if heartbeat:
        match.lease_until = timezone.now() + timedelta(seconds=ops.LEASE_SECONDS)
        match.save(update_fields=['lease_until'])
    else:
        if not isinstance(result,dict):
            raise ValueError('Kết quả không hợp lệ.')
        if result.get('infrastructure_error'):
            match.state = 'failed'; match.message = 'Máy chấm gặp lỗi. Bạn có thể tạo trận mới khi hệ thống sẵn sàng.'
        else:
            if (result.get('id') != f'job-practice-{match.pk}' or result.get('result') not in ('win','forfeit','draw')
                    or (result['result']=='draw' and result.get('winner') is not None)
                    or (result['result']!='draw' and result.get('winner') not in ('P1','P2'))):
                raise ValueError('Kết quả trận không hợp lệ.')
            match.state = 'completed'
            try:
                from .models import update_user_elo_solo, update_elo_after_match, UserProfile
                winner_side = result.get('winner')
                outcome = result.get('result')
                if outcome == 'draw' or winner_side is None:
                    won = None
                elif winner_side == match.player_side:
                    won = True
                else:
                    won = False

                opponent_user = None
                if match.opponent_label and match.opponent_label.startswith('submission:'):
                    try:
                        sub_id = int(match.opponent_label.split(':')[1])
                        from submissions.models import Submission
                        opp_sub = Submission.objects.select_related('submitter').get(pk=sub_id)
                        if opp_sub.submitter != match.user:
                            opponent_user = opp_sub.submitter
                    except Exception:
                        pass

                if opponent_user:
                    if won is True:
                        update_elo_after_match(match.user, opponent_user)
                    elif won is False:
                        update_elo_after_match(opponent_user, match.user)
                    else:
                        p1, _ = UserProfile.objects.get_or_create(user=match.user)
                        p2, _ = UserProfile.objects.get_or_create(user=opponent_user)
                        p1.draws += 1
                        p1.save(update_fields=['draws', 'updated_at'])
                        p2.draws += 1
                        p2.save(update_fields=['draws', 'updated_at'])
                else:
                    update_user_elo_solo(match.user, won)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning('Practice match ELO update failed: %s', e)
        match.result = result; match.finished_at = timezone.now(); match.lease_until = None
        match.save()
    JudgeWorker.objects.filter(pk=worker.pk).update(last_seen=timezone.now())
    return match
