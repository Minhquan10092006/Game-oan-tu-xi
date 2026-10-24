"""Single-server judge runner. No remote worker token is involved."""
from __future__ import annotations

import hashlib
import time
import threading

from django.db import close_old_connections

from matches.judge_worker import execute
from matches.tournament import engine_hash
from .models import JudgeWorker
from . import tournament_ops as ops, practice_ops


def _worker():
    # token_hash remains only to keep old database rows/migrations compatible;
    # it is a fixed marker, never issued or used for local judging.
    return JudgeWorker.objects.get_or_create(
        slot=1, defaults={'name': 'Sandbox của server', 'token_hash': hashlib.sha256(b'local').hexdigest()},
    )[0]


def run_once():
    close_old_connections()
    worker = _worker()
    job = practice_ops.claim(worker.pk, engine_hash())
    if not job:
        return False
    practice = str(job['id']).startswith('practice-')
    stop = threading.Event()
    lost = threading.Event()

    def renew():
        while not stop.wait(25):
            close_old_connections()
            try:
                if practice:
                    practice_ops.update(worker, job['id'], job['lease_token'], heartbeat=True)
                else:
                    ops.heartbeat(worker, job['id'], job['lease_token'])
            except ValueError:
                lost.set()
                return
            except Exception:
                # A transient database error may recover before lease expiry.
                pass
            finally:
                close_old_connections()

    heartbeat = threading.Thread(target=renew, daemon=True)
    heartbeat.start()
    try:
        try:
            result = execute(job)
        except Exception as exc:
            result = {'infrastructure_error': True, 'message': f'{type(exc).__name__}: {exc}'[:2000]}
        if not lost.is_set():
            if practice:
                practice_ops.update(worker, job['id'], job['lease_token'], result)
            else:
                ops.finish_job(worker, job['id'], job['lease_token'], result)
    finally:
        stop.set()
        heartbeat.join(timeout=5)
    return True


def run_until_empty(wait=False):
    while True:
        if run_once():
            continue
        if not wait:
            return
        time.sleep(2)
