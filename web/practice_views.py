import uuid
import threading
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from matches.practice_bots import BOTS
from submissions.models import Submission
from .models import PracticeMatch, JudgeWorker
from .tournament_ops import can_operate
from . import practice_ops


@login_required(login_url='/login/')
@ensure_csrf_cookie
def page(request):
    if can_operate(request.user):
        return redirect('/tournament/')
    return render(request, 'web/practice.html', {'page':'practice'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def options(request):
    mine = Submission.objects.filter(submitter=request.user).exclude(review_status='rejected').order_by('-submitted_at')
    opponents = Submission.objects.filter(review_status='approved').order_by('-submitted_at')
    search = str(request.query_params.get('q',''))[:80].strip()
    if search:
        opponents = opponents.filter(Q(ai_name__icontains=search) | Q(submitter__username__icontains=search))
    used = PracticeMatch.objects.filter(user=request.user, created_at__date=timezone.localdate()).count()
    response = Response({'mine':list(mine.values('id','ai_name','version','review_status')[:100]),
        'samples':[{'key':'sample:'+key,'label':bot['name'],'description':bot['description']} for key,bot in BOTS.items()],
        'opponents':[{'key':f'submission:{row["id"]}','label':f'{row["ai_name"]} v{row["version"]} · {row["submitter__username"]}'}
            for row in opponents.values('id','ai_name','version','submitter__username')[:100]],
        'limit':settings.PRACTICE_MATCHES_PER_DAY,'used':used,
        'local_judge':settings.LOCAL_JUDGE_AUTOSTART,
        'online_workers':JudgeWorker.objects.filter(enabled=True,last_seen__gt=timezone.now()-timedelta(seconds=90)).count()})
    response['Cache-Control'] = 'no-store'
    return response


def rows(user):
    result = list(PracticeMatch.objects.filter(user=user).order_by('-pk').values(
        'id','own_label','opponent_label','player_side','state','message','created_at','finished_at',
        'result__winner','result__result')[:30])
    for row in result:
        winner, outcome = row.pop('result__winner'), row.pop('result__result')
        row['outcome'] = ('draw' if outcome == 'draw' else 'win' if winner == row['player_side'] else 'loss') if row['state'] == 'completed' else ''
    return result


@api_view(['GET','POST'])
@permission_classes([IsAuthenticated])
def matches(request):
    if request.method == 'GET':
        response = Response(rows(request.user)); response['Cache-Control']='no-store'; return response
    if can_operate(request.user) or request.session.get('is_guest'):
        return Response({'error':'Dùng tài khoản sinh viên chính thức để luyện tập.'},status=403)
    try:
        client_id = uuid.UUID(str(request.data.get('request_id','')))
        submission_id = int(request.data.get('submission_id'))
        opponent = str(request.data.get('opponent',''))
        if len(opponent)>80:
            raise ValueError('Đối thủ không hợp lệ.')
        match, created = practice_ops.create(request.user,client_id,submission_id,opponent,str(request.data.get('side','P1')))
    except (ValueError,TypeError) as error:
        return Response({'error':str(error) or 'Lựa chọn không hợp lệ.'},status=409)
    if created and settings.LOCAL_JUDGE_AUTOSTART:
        from .local_judge import run_until_empty
        transaction.on_commit(lambda: threading.Thread(target=run_until_empty, daemon=True).start())
    return Response({'id':match.pk,'state':match.state},status=201 if created else 200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel(request, match_id):
    with transaction.atomic():
        match = get_object_or_404(PracticeMatch.objects.select_for_update(),pk=match_id,user=request.user)
        if match.state != 'queued':
            return Response({'error':'Chỉ hủy được trận còn đang chờ.'},status=409)
        match.state='cancelled';match.message='Bạn đã hủy trận chờ.';match.save(update_fields=['state','message'])
    return Response({'ok':True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def replay(request, match_id):
    match = get_object_or_404(PracticeMatch,pk=match_id,user=request.user,state='completed')
    # Opponent traceback/debug can reveal their private source. Only release
    # the caller's stderr; game states and timing are sufficient for replay.
    result = {key:value for key,value in match.result.items() if key in (
        'id','rules_version','status','board_preset','ply','winner','result','reason','events','state','bot_runs')}
    result['bot_runs'] = [{key:value for key,value in run.items()
        if key in ('player','elapsed_ms','exit_code','error') or (key == 'stderr' and run.get('player') == match.player_side)}
        for run in result.get('bot_runs',[]) if isinstance(run,dict)]
    response=Response(result);response['Cache-Control']='no-store';return response
