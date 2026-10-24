"""Single-server judge runner. No remote worker token is involved."""
from __future__ import annotations

import hashlib
import time

from django.db import close_old_connections

from matches.judge_worker import execute
from matches.tournament import engine_hash
from .models import JudgeWorker
from . import tournament_ops as ops


def _worker():
    # token_hash remains only to keep old database rows/migrations compatible;
    # it is a fixed marker, never issued or used for local judging.
    return JudgeWorker.objects.get_or_create(
        slot=1, defaults={'name': 'Sandbox của server', 'token_hash': hashlib.sha256(b'local').hexdigest()},
    )[0]


def run_once():
    close_old_connections()
    worker = _worker()
    job = ops.claim_job(worker.pk, engine_hash())
    if not job:
        return False
    try:
        result = execute(job)
    except Exception as exc:
        result = {'infrastructure_error': True, 'message': f'{type(exc).__name__}: {exc}'[:2000]}
    ops.finish_job(worker, job['id'], job['lease_token'], result)
    return True


def run_until_empty(wait=False):
    while True:
        if run_once():
            continue
        if not wait:
            return
        time.sleep(2)
