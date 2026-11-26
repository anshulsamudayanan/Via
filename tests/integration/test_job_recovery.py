"""Recovery of import jobs whose worker died or whose queued job was lost.

Stage 2 audit finding D1: killing the worker mid-parse left the revision "processing"
forever. These tests cover the reaper logic directly and, in the last test, with a
real worker process that is SIGKILLed in the middle of a parse.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from tests.integration.conftest import register
from via_api import jobs
from via_api.config import Settings
from via_api.db import get_db
from via_api.deps import get_job_queue
from via_api.models import AnalysisRun, DesignRevision
from via_api.models.base import utcnow
from via_api.models.enums import AnalysisKind, AnalysisStatus, RevisionStatus

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_bytes()


@pytest.fixture
def uploaded(client, job_queue):
    """A revision that has been uploaded and queued but not processed."""
    job_queue.run = False
    register(client, "recovery@example.com")
    project = client.post("/api/v1/projects", json={"name": "Recovery"}).json()
    resp = client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("board.kicad_pcb", REF, "application/octet-stream")},
    )
    assert resp.status_code == 202
    job_queue.enqueued.clear()
    job_queue.attempts.clear()
    return uuid.UUID(resp.json()["revision"]["id"])


def crash_mid_job(db: Session, revision_id: uuid.UUID, attempt: int, seconds_ago: int) -> AnalysisRun:
    """Put the revision in the state a worker leaves behind when it dies mid-parse."""
    revision = db.get(DesignRevision, revision_id)
    revision.status = RevisionStatus.PROCESSING
    run = jobs.import_run(db, revision)
    run.status = AnalysisStatus.RUNNING
    run.attempt = attempt
    run.job_id = jobs.import_job_id(revision_id, attempt)
    run.started_at = run.heartbeat_at = utcnow() - timedelta(seconds=seconds_ago)
    db.commit()
    return run


def status(client, revision_id):
    return client.get(f"/api/v1/revisions/{revision_id}").json()


def test_stale_running_import_is_requeued_with_a_new_attempt(client, db, uploaded, job_queue, settings):
    crash_mid_job(db, uploaded, attempt=1, seconds_ago=settings.job_stale_after_seconds + 5)
    report = jobs.reap_imports(db, job_queue, settings)
    assert report.requeued == [uploaded] and report.failed == []
    assert job_queue.enqueued == [uploaded] and job_queue.attempts == [2]
    run = jobs.import_run(db, db.get(DesignRevision, uploaded))
    assert (run.status, run.attempt, run.job_id) == (AnalysisStatus.QUEUED, 2, f"import-{uploaded}-a2")
    assert status(client, uploaded)["status"] == "pending"


def test_requeued_attempt_completes_normally(client, db, uploaded, job_queue, settings):
    crash_mid_job(db, uploaded, attempt=1, seconds_ago=settings.job_stale_after_seconds + 5)
    job_queue.run = True
    jobs.reap_imports(db, job_queue, settings)
    rev = status(client, uploaded)
    assert rev["status"] == "ready"
    assert rev["object_counts"]["component_count"] == 4
    assert jobs.import_run(db, db.get(DesignRevision, uploaded)).attempt == 2


def test_import_fails_with_worker_lost_after_max_attempts(client, db, uploaded, job_queue, settings):
    crash_mid_job(db, uploaded, attempt=settings.job_max_attempts, seconds_ago=settings.job_stale_after_seconds + 5)
    report = jobs.reap_imports(db, job_queue, settings)
    assert report.failed == [uploaded] and job_queue.enqueued == []
    rev = status(client, uploaded)
    assert rev["status"] == "failed"
    assert rev["error_code"] == "worker_lost"
    assert "Try uploading" in rev["error_message"]


def test_recent_heartbeat_is_left_alone(db, uploaded, job_queue, settings):
    crash_mid_job(db, uploaded, attempt=1, seconds_ago=settings.job_stale_after_seconds - 30)
    report = jobs.reap_imports(db, job_queue, settings)
    assert report.requeued == [] and report.failed == []
    assert db.get(DesignRevision, uploaded).status == RevisionStatus.PROCESSING


def test_lost_pending_job_is_requeued(db, uploaded, job_queue, settings):
    later = utcnow() + timedelta(seconds=settings.job_lost_after_seconds + 5)
    report = jobs.reap_imports(db, job_queue, settings, now=later)  # the a1 job isn't in the queue
    assert report.requeued == [uploaded]
    assert job_queue.attempts == [2]


def test_pending_job_still_in_the_queue_is_left_alone(db, uploaded, job_queue, settings):
    job_queue.alive.add(jobs.import_job_id(uploaded, 1))
    later = utcnow() + timedelta(seconds=settings.job_lost_after_seconds + 5)
    assert jobs.reap_imports(db, job_queue, settings, now=later).requeued == []


def test_recently_uploaded_pending_job_is_left_alone(db, uploaded, job_queue, settings):
    assert jobs.reap_imports(db, job_queue, settings).requeued == []


def test_failure_callback_from_a_superseded_attempt_is_ignored(client, db, uploaded, job_queue, settings, monkeypatch):
    crash_mid_job(db, uploaded, attempt=1, seconds_ago=settings.job_stale_after_seconds + 5)
    jobs.reap_imports(db, job_queue, settings)  # attempt 2 queued
    monkeypatch.setattr(jobs, "_session", lambda _s: (db, SimpleNamespace(dispose=lambda: None)))
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "close", lambda: None)
    # RQ eventually notices the dead attempt-1 job and runs its failure callback.
    old_job = SimpleNamespace(id=jobs.import_job_id(uploaded, 1), args=[str(uploaded), 1])
    jobs.on_import_failure(old_job, None, RuntimeError, RuntimeError("abandoned"), None)
    assert status(client, uploaded)["status"] == "pending"
    # The current attempt's failure still counts.
    new_job = SimpleNamespace(id=jobs.import_job_id(uploaded, 2), args=[str(uploaded), 2])
    jobs.on_import_failure(new_job, None, RuntimeError, RuntimeError("crash"), None)
    assert status(client, uploaded)["status"] == "failed"


def test_heartbeat_refreshes_the_running_run(db, uploaded, settings):
    run = crash_mid_job(db, uploaded, attempt=1, seconds_ago=600)
    old = run.heartbeat_at
    jobs.Heartbeat(settings, uploaded).beat(db)
    db.refresh(run)
    assert run.heartbeat_at > old


def test_rq_job_alive(settings, test_redis):
    queue = jobs.RQJobQueue(test_redis, settings)
    rid = uuid.uuid4()
    assert not queue.job_alive(jobs.import_job_id(rid, 1))
    queue.enqueue_import(rid)
    assert queue.job_alive(jobs.import_job_id(rid, 1))
    queue.queue.fetch_job(jobs.import_job_id(rid, 1)).delete()
    assert not queue.job_alive(jobs.import_job_id(rid, 1))


def test_job_timing_settings_are_validated(database_url):
    with pytest.raises(ValueError, match="at least 3x"):
        Settings(env="test", database_url=database_url, job_heartbeat_seconds=10, job_stale_after_seconds=20)


# --- A real worker, really killed -------------------------------------------------------------


def slow_board(segments: int) -> bytes:
    """The reference board plus many extra segments, so parsing takes several seconds."""
    extra = "".join(
        f"\t(segment (start {100 + i % 40} {101 + (i // 40) % 25}) (end {101 + i % 40} {101 + (i // 40) % 25}) "
        f'(width 0.2) (layer "In1.Cu") (net 0) (uuid "{uuid.UUID(int=i)}"))\n'
        for i in range(segments)
    )
    body = REF.decode().rstrip()
    assert body.endswith(")")
    return (body[:-1] + extra + ")\n").encode()


@pytest.fixture
def committed(migrated_engine, settings, test_redis, mailer):
    """An app whose database writes are committed, so a separate worker process can see them."""
    from via_api.deps import get_email_sender
    from via_api.main import create_app
    from via_api.redis_client import get_redis
    from via_api.storage import LocalStorage, get_storage

    queue_name = f"via-test-{uuid.uuid4().hex[:8]}"
    settings = settings.model_copy(update={"import_queue_name": queue_name})
    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    app = create_app(settings)

    def db_dep():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    from via_api.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_redis] = lambda: test_redis
    app.dependency_overrides[get_storage] = lambda: LocalStorage(settings.local_storage_path)
    app.dependency_overrides[get_email_sender] = lambda: mailer
    app.dependency_overrides[get_job_queue] = lambda: jobs.RQJobQueue(test_redis, settings)
    email = f"crash-{uuid.uuid4().hex[:8]}@example.com"
    with TestClient(app, headers={"X-VIA-Request": "1"}) as c:
        me = register(c, email)
        yield SimpleNamespace(client=c, settings=settings, factory=factory, user_id=me["user"]["id"])
    with migrated_engine.begin() as conn:  # leave the shared test database as we found it
        conn.execute(text("DELETE FROM projects WHERE owner_id = :u"), {"u": me["user"]["id"]})
        conn.execute(
            text("DELETE FROM organizations WHERE id IN (SELECT organization_id FROM organization_memberships "
                 "WHERE user_id = :u)"),
            {"u": me["user"]["id"]},
        )  # fmt: skip
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": me["user"]["id"]})


def descendants(pid: int) -> list[int]:
    """All descendant pids (the RQ work-horse moves to its own process group, so killpg misses it)."""
    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                ppid = int((entry / "stat").read_text().rsplit(")", 1)[1].split()[1])
            except (OSError, IndexError, ValueError):
                continue
            children.setdefault(ppid, []).append(int(entry.name))
    out, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            out.append(child)
            todo.append(child)
    return out


def kill_tree(pid: int) -> None:
    for p in [pid, *descendants(pid)]:
        with contextlib.suppress(ProcessLookupError):
            os.kill(p, signal.SIGKILL)


def worker_env(settings: Settings) -> dict[str, str]:
    return {
        **os.environ,
        "VIA_ENV": "test",
        "VIA_DATABASE_URL": settings.database_url,
        "VIA_REDIS_URL": settings.redis_url,
        "VIA_STORAGE_BACKEND": "local",
        "VIA_LOCAL_STORAGE_PATH": str(settings.local_storage_path),
        "VIA_IMPORT_QUEUE_NAME": settings.import_queue_name,
        "VIA_PARSER_TIMEOUT_SECONDS": "120",
        "VIA_JOB_HEARTBEAT_SECONDS": "1",
        "VIA_JOB_STALE_AFTER_SECONDS": "5",
        "VIA_JOB_REAPER_INTERVAL_SECONDS": "3600",  # the test drives the reaper itself (after startup)
    }


def run_status(factory, revision_id) -> tuple[RevisionStatus, AnalysisRun | None]:
    with factory() as s:
        rev = s.get(DesignRevision, revision_id)
        run = s.scalar(
            select(AnalysisRun).where(
                AnalysisRun.revision_id == revision_id, AnalysisRun.kind == AnalysisKind.PCB_IMPORT
            )
        )
        return rev.status, run


def test_killed_worker_is_recovered_end_to_end(committed):
    c, settings = committed.client, committed.settings
    project = c.post("/api/v1/projects", json={"name": "Crash"}).json()
    resp = c.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("slow.kicad_pcb", slow_board(120_000), "application/octet-stream")},
    )
    assert resp.status_code == 202, resp.text
    rid = uuid.UUID(resp.json()["revision"]["id"])
    cli = [sys.executable, "-m", "via_api.cli", "worker", "--burst"]

    # Start a real worker and SIGKILL it (and its work-horse and parser) mid-parse.
    worker = subprocess.Popen(cli, env=worker_env(settings), start_new_session=True)  # noqa: S603
    try:
        deadline = time.monotonic() + 60
        while run_status(committed.factory, rid)[0] != RevisionStatus.PROCESSING:
            assert time.monotonic() < deadline, "worker never started the job"
            assert worker.poll() is None, "worker exited before it was killed"
            time.sleep(0.2)
        time.sleep(2.5)  # let it beat at least once
        kill_tree(worker.pid)  # like a container being killed: worker, work-horse and parser
    finally:
        worker.wait(timeout=30)

    state, run = run_status(committed.factory, rid)
    assert state == RevisionStatus.PROCESSING  # the bug: nothing else would ever change this
    assert run is not None and run.attempt == 1 and run.heartbeat_at is not None

    # After the heartbeat goes stale, the reaper re-queues attempt 2 and a new worker finishes it.
    time.sleep(6)
    with committed.factory() as s:
        report = jobs.reap_imports(s, jobs.RQJobQueue(_redis(settings), settings), settings.model_copy(
            update={"job_stale_after_seconds": 5, "job_heartbeat_seconds": 1}
        ))  # fmt: skip
    assert report.requeued == [rid]
    subprocess.run(cli, env=worker_env(settings), check=True, timeout=180)  # noqa: S603
    state, run = run_status(committed.factory, rid)
    assert state == RevisionStatus.READY
    assert run.attempt == 2 and run.status == AnalysisStatus.SUCCEEDED
    assert c.get(f"/api/v1/revisions/{rid}").json()["object_counts"]["track_count"] == 8 + 120_000


def _redis(settings: Settings):
    from redis import Redis

    return Redis.from_url(settings.redis_url)


def test_abandoned_job_reported_by_rq_is_retried_then_failed(client, db, uploaded, job_queue, settings, monkeypatch):
    """RQ's registry cleanup reports a job whose worker died as AbandonedJobError (seen in the audit)."""
    from rq.exceptions import AbandonedJobError

    monkeypatch.setattr(jobs, "_session", lambda _s: (db, SimpleNamespace(dispose=lambda: None)))
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(jobs, "RQJobQueue", lambda _conn, _settings: job_queue)
    monkeypatch.setattr(db, "close", lambda: None)
    for attempt in range(1, settings.job_max_attempts):
        crash_mid_job(db, uploaded, attempt=attempt, seconds_ago=1)
        job = SimpleNamespace(id=jobs.import_job_id(uploaded, attempt), args=[str(uploaded), attempt])
        jobs.on_import_failure(job, None, AbandonedJobError, AbandonedJobError(), None)
        assert status(client, uploaded)["status"] == "pending"
        assert job_queue.attempts[-1] == attempt + 1
    last = settings.job_max_attempts
    crash_mid_job(db, uploaded, attempt=last, seconds_ago=1)
    job = SimpleNamespace(id=jobs.import_job_id(uploaded, last), args=[str(uploaded), last])
    jobs.on_import_failure(job, None, AbandonedJobError, AbandonedJobError(), None)
    rev = status(client, uploaded)
    assert (rev["status"], rev["error_code"]) == ("failed", "worker_lost")
