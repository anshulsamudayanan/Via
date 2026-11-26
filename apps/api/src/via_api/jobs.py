"""Background job queue (RQ on Redis), job entry points and job recovery.

The API enqueues; the worker (``via-api worker``) runs jobs in a forked
process per job. Each job builds its own database session and storage client
from settings. The parser itself runs in a further, credential-free sandbox
subprocess (see ``parsing/sandbox.py``).

Recovery. RQ's failure callback only fires when the worker survives the failure.
If the whole worker dies (OOM kill, container restart, host crash), or Redis loses
queued jobs (it runs without persistence in Compose), the database would say
"processing"/"pending" forever. So:

* a running job refreshes ``analysis_runs.heartbeat_at`` from a background thread;
* every worker runs a *reaper* that re-queues imports whose heartbeat went stale or
  whose queued job no longer exists, up to ``job_max_attempts`` tries, and then
  marks the revision failed with ``worker_lost``;
* each attempt has its own job id, and callbacks from superseded attempts are ignored.

RQ's own registry cleanup reports jobs whose worker died as ``AbandonedJobError``;
the failure callback treats that like a stale heartbeat (retry, then ``worker_lost``).

Imports are idempotent (``process_revision`` replaces earlier rows), so a retry after a
partially completed attempt is safe.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from redis import Redis
from rq import Callback, Queue, Worker
from rq.exceptions import AbandonedJobError, NoSuchJobError
from rq.job import Job, JobStatus
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

from via_api.config import Settings, get_settings
from via_api.models import AnalysisRun, DesignRevision
from via_api.models.base import utcnow
from via_api.models.enums import AnalysisKind, AnalysisStatus, RevisionStatus
from via_api.parsing.importer import import_run, mark_failed, process_revision
from via_api.parsing.sandbox import SandboxLimits
from via_api.services.analysis import analysis_job_id, fail_run, process_analysis
from via_api.storage import get_storage

logger = logging.getLogger("via_api.jobs")

WORKER_LOST_ANALYSIS_MESSAGE = (
    "The analysis was interrupted repeatedly (the worker stopped or ran out of resources). Try running it again."
)
WORKER_LOST_MESSAGE = (
    "Processing was interrupted repeatedly (the worker stopped or ran out of resources). Try uploading the file again."
)


def import_job_id(revision_id: uuid.UUID | str, attempt: int) -> str:
    return f"import-{revision_id}-a{attempt}"


class JobQueue(Protocol):
    def enqueue_import(self, revision_id: uuid.UUID, attempt: int = 1) -> None: ...

    def enqueue_analysis(self, run_id: uuid.UUID, attempt: int = 1) -> None: ...

    def job_alive(self, job_id: str) -> bool: ...


#: RQ states in which a job will still run (or is running).
_ALIVE = {JobStatus.QUEUED, JobStatus.STARTED, JobStatus.DEFERRED, JobStatus.SCHEDULED}


class RQJobQueue:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.redis = redis
        self.queue = Queue(settings.import_queue_name, connection=redis)
        # The job outlives the parser's own timeout (download + persist time).
        self.job_timeout = settings.parser_timeout_seconds + 120
        # An analysis may first re-import an outdated revision, then run the checks.
        self.analysis_timeout = settings.parser_timeout_seconds + settings.analysis_timeout_seconds + 120

    def enqueue_import(self, revision_id: uuid.UUID, attempt: int = 1) -> None:
        self.queue.enqueue(
            "via_api.jobs.import_revision",
            str(revision_id),
            attempt,
            job_timeout=self.job_timeout,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            on_failure=Callback("via_api.jobs.on_import_failure", timeout=60),
            job_id=import_job_id(revision_id, attempt),
        )

    def enqueue_analysis(self, run_id: uuid.UUID, attempt: int = 1) -> None:
        self.queue.enqueue(
            "via_api.jobs.analyze_run",
            str(run_id),
            attempt,
            job_timeout=self.analysis_timeout,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            on_failure=Callback("via_api.jobs.on_analysis_failure", timeout=60),
            job_id=analysis_job_id(run_id, attempt),
        )

    def job_alive(self, job_id: str) -> bool:
        try:
            job = Job.fetch(job_id, connection=self.redis)
        except NoSuchJobError:
            return False
        return job.get_status(refresh=False) in _ALIVE


def sandbox_limits(settings: Settings) -> SandboxLimits:
    return SandboxLimits(
        timeout_seconds=settings.parser_timeout_seconds,
        memory_bytes=settings.parser_memory_limit_mb * 1024 * 1024,
        # A board inside a project archive may be as large as a directly uploaded one.
        max_archive_board_bytes=settings.max_upload_bytes,
    )


def _session(settings: Settings) -> tuple[Session, Any]:
    engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"})
    return Session(bind=engine, expire_on_commit=False), engine


class Heartbeat:
    """Refreshes ``heartbeat_at`` until stopped: on one run (``run_id``), or on the running
    import run of a revision (imports create their run inside the job)."""

    def __init__(
        self, settings: Settings, revision_id: uuid.UUID | None = None, *, run_id: uuid.UUID | None = None
    ) -> None:
        if (revision_id is None) == (run_id is None):
            raise ValueError("pass exactly one of revision_id and run_id")
        self.settings = settings
        self.revision_id = revision_id
        self.run_id = run_id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{revision_id or run_id}", daemon=True)

    def beat(self, db: Session) -> None:
        if self.run_id is not None:
            target = AnalysisRun.id == self.run_id
        else:
            target = (AnalysisRun.revision_id == self.revision_id) & (AnalysisRun.kind == AnalysisKind.PCB_IMPORT)
        db.execute(
            update(AnalysisRun)
            .where(target, AnalysisRun.status == AnalysisStatus.RUNNING)
            .values(heartbeat_at=func.now())
        )
        db.commit()

    def _run(self) -> None:
        db, engine = _session(self.settings)
        try:
            while not self._stop.wait(self.settings.job_heartbeat_seconds):
                try:
                    self.beat(db)
                except Exception:  # a missed beat is tolerated; the reaper allows several
                    db.rollback()
                    logger.warning("Heartbeat for %s failed", self.revision_id, exc_info=True)
        finally:
            db.close()
            engine.dispose()

    def __enter__(self) -> Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


def import_revision(revision_id: str, attempt: int = 1) -> str:
    """RQ job: parse and persist one uploaded revision."""
    from rq import get_current_job

    settings = get_settings()
    current = get_current_job()
    db, engine = _session(settings)
    try:
        with Heartbeat(settings, uuid.UUID(revision_id)):
            revision = process_revision(
                db,
                get_storage(),
                uuid.UUID(revision_id),
                sandbox_limits(settings),
                attempt=attempt,
                job_id=current.id if current else import_job_id(revision_id, attempt),
            )
        return revision.status.value if revision else "missing"
    finally:
        db.close()
        engine.dispose()


def on_import_failure(job: Any, connection: Any, type: Any, value: Any, traceback: Any) -> None:
    """RQ failure callback (job crashed or timed out): never leave a revision stuck in processing."""
    settings = get_settings()
    db, engine = _session(settings)
    try:
        revision = db.get(DesignRevision, uuid.UUID(job.args[0]))
        if revision is None or revision.status not in (RevisionStatus.PENDING, RevisionStatus.PROCESSING):
            return
        run = import_run(db, revision)
        job_id = getattr(job, "id", None)
        if run.job_id and job_id and run.job_id != job_id:
            logger.info("Ignoring failure of superseded job %s (current: %s)", job_id, run.job_id)
            return
        if type is AbandonedJobError:
            # RQ found the job's worker dead (its registry cleanup): same as a stale heartbeat.
            logger.warning("Import job %s for %s was abandoned by its worker", job_id, revision.id)
            _retry_or_fail(db, RQJobQueue(connection, settings), revision, run, settings, ReapReport())
            return
        logger.error("Import job for %s failed: %s", revision.id, type.__name__ if type else "unknown")
        mark_failed(db, revision, "processing_failed", "Processing stopped unexpectedly. Try uploading the file again.")
        db.commit()
    finally:
        db.close()
        engine.dispose()


def analyze_run(run_id: str, attempt: int = 1) -> str:
    """RQ job: execute one analysis run."""
    from rq import get_current_job

    settings = get_settings()
    current = get_current_job()
    db, engine = _session(settings)
    storage = get_storage()

    def reimport(revision_id: uuid.UUID) -> None:
        process_revision(db, storage, revision_id, sandbox_limits(settings))

    try:
        with Heartbeat(settings, run_id=uuid.UUID(run_id)):
            run = process_analysis(
                db,
                storage,
                uuid.UUID(run_id),
                reimport=reimport,
                attempt=attempt,
                job_id=current.id if current else analysis_job_id(run_id, attempt),
            )
        return run.status.value if run else "missing"
    finally:
        db.close()
        engine.dispose()


def on_analysis_failure(job: Any, connection: Any, type: Any, value: Any, traceback: Any) -> None:
    """RQ failure callback for analysis jobs (crash, timeout, abandoned)."""
    settings = get_settings()
    db, engine = _session(settings)
    try:
        run = db.get(AnalysisRun, uuid.UUID(job.args[0]))
        if run is None or run.status not in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING):
            return
        job_id = getattr(job, "id", None)
        if run.job_id and job_id and run.job_id != job_id:
            return  # superseded attempt
        if type is AbandonedJobError:
            _retry_or_fail_analysis(db, RQJobQueue(connection, settings), run, settings, ReapReport())
            return
        logger.error("Analysis job %s failed: %s", run.id, type.__name__ if type else "unknown")
        code = "timeout" if type is not None and "Timeout" in type.__name__ else "analysis_failed"
        fail_run(db, run, code, "The analysis stopped unexpectedly. Try running it again.")
        db.commit()
    finally:
        db.close()
        engine.dispose()


def _retry_or_fail_analysis(
    db: Session, queue: JobQueue, run: AnalysisRun, settings: Settings, report: ReapReport
) -> None:
    tried = max(run.attempt, 1)
    if tried >= settings.job_max_attempts:
        logger.error("Analysis run %s lost after %d attempts; marking failed", run.id, tried)
        fail_run(db, run, "worker_lost", WORKER_LOST_ANALYSIS_MESSAGE)
        db.commit()
        report.failed.append(run.id)
        return
    nxt = tried + 1
    run.status = AnalysisStatus.QUEUED
    run.attempt = nxt
    run.job_id = analysis_job_id(run.id, nxt)
    run.heartbeat_at = None
    db.commit()
    try:
        queue.enqueue_analysis(run.id, attempt=nxt)
    except Exception:
        logger.warning("Could not re-queue analysis run %s; will retry", run.id, exc_info=True)
        return
    logger.warning("Re-queued analysis run %s (attempt %d of %d)", run.id, nxt, settings.job_max_attempts)
    report.requeued.append(run.id)


def reap_analyses(db: Session, queue: JobQueue, settings: Settings, now: datetime | None = None) -> ReapReport:
    """Recover analysis runs whose worker died (stale heartbeat) or whose queued job was lost."""
    now = now or utcnow()
    report = ReapReport()
    stale_before = now - timedelta(seconds=settings.job_stale_after_seconds)
    stale = db.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
            AnalysisRun.status == AnalysisStatus.RUNNING,
            func.coalesce(AnalysisRun.heartbeat_at, AnalysisRun.started_at) < stale_before,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for run in stale:
        logger.warning("Analysis run %s has a stale heartbeat (job %s)", run.id, run.job_id)
        _retry_or_fail_analysis(db, queue, run, settings, report)
    lost_before = now - timedelta(seconds=settings.job_lost_after_seconds)
    queued = db.scalars(
        select(AnalysisRun)
        .where(
            AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
            AnalysisRun.status == AnalysisStatus.QUEUED,
            AnalysisRun.updated_at < lost_before,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for run in queued:
        if queue.job_alive(run.job_id or analysis_job_id(run.id, max(run.attempt, 1))):
            continue
        logger.warning("Queued analysis run %s is missing from the queue", run.id)
        _retry_or_fail_analysis(db, queue, run, settings, report)
    db.commit()
    return report


@dataclass
class ReapReport:
    requeued: list[uuid.UUID] = field(default_factory=list)
    failed: list[uuid.UUID] = field(default_factory=list)


def _retry_or_fail(
    db: Session, queue: JobQueue, revision: DesignRevision, run: AnalysisRun, settings: Settings, report: ReapReport
) -> None:
    tried = max(run.attempt, 1)
    if tried >= settings.job_max_attempts:
        logger.error("Import of revision %s lost after %d attempts; marking failed", revision.id, tried)
        mark_failed(db, revision, "worker_lost", WORKER_LOST_MESSAGE)
        db.commit()
        report.failed.append(revision.id)
        return
    nxt = tried + 1
    revision.status = RevisionStatus.PENDING
    run.status = AnalysisStatus.QUEUED
    run.attempt = nxt
    run.job_id = import_job_id(revision.id, nxt)
    run.heartbeat_at = None
    db.commit()  # commit first: the new attempt must see the queued state
    try:
        queue.enqueue_import(revision.id, attempt=nxt)
    except Exception:
        # Redis down: the revision stays pending with a job id that doesn't exist,
        # so a later reaper pass picks it up again.
        logger.warning("Could not re-queue revision %s; will retry", revision.id, exc_info=True)
        return
    logger.warning("Re-queued import of revision %s (attempt %d of %d)", revision.id, nxt, settings.job_max_attempts)
    report.requeued.append(revision.id)


def reap_imports(db: Session, queue: JobQueue, settings: Settings, now: datetime | None = None) -> ReapReport:
    """Recover imports whose worker died or whose queued job was lost. Safe to run concurrently."""
    now = now or utcnow()
    report = ReapReport()

    # 1. Running, but no heartbeat for too long: the worker died mid-job.
    stale_before = now - timedelta(seconds=settings.job_stale_after_seconds)
    stale = db.execute(
        select(AnalysisRun, DesignRevision)
        .join(DesignRevision, DesignRevision.id == AnalysisRun.revision_id)
        .where(
            AnalysisRun.kind == AnalysisKind.PCB_IMPORT,
            AnalysisRun.status == AnalysisStatus.RUNNING,
            func.coalesce(AnalysisRun.heartbeat_at, AnalysisRun.started_at) < stale_before,
            DesignRevision.status == RevisionStatus.PROCESSING,
        )
        .with_for_update(skip_locked=True, of=AnalysisRun)
    ).all()
    for run, revision in stale:
        logger.warning("Import of revision %s has a stale heartbeat (job %s)", revision.id, run.job_id)
        _retry_or_fail(db, queue, revision, run, settings, report)

    # 2. Pending for a while, but the queued job no longer exists (Redis restarted or flushed).
    lost_before = now - timedelta(seconds=settings.job_lost_after_seconds)
    pending = db.scalars(
        select(DesignRevision)
        .where(DesignRevision.status == RevisionStatus.PENDING, DesignRevision.updated_at < lost_before)
        .with_for_update(skip_locked=True)
    ).all()
    for revision in pending:
        run = import_run(db, revision)
        if run.updated_at is not None and run.updated_at >= lost_before:
            continue  # re-queued recently
        job_id = run.job_id or import_job_id(revision.id, max(run.attempt, 1))
        if queue.job_alive(job_id):
            continue
        logger.warning("Queued import of revision %s is missing from the queue (job %s)", revision.id, job_id)
        _retry_or_fail(db, queue, revision, run, settings, report)
    db.commit()
    return report


def reap_once(settings: Settings, queue: JobQueue) -> None:
    """One reaper pass with its own session; never raises (the worker must keep running)."""
    db, engine = _session(settings)
    try:
        imports = reap_imports(db, queue, settings)
        analyses = reap_analyses(db, queue, settings)
        report = ReapReport(imports.requeued + analyses.requeued, imports.failed + analyses.failed)
        if report.requeued or report.failed:
            logger.warning("Reaper: requeued %d, failed %d", len(report.requeued), len(report.failed))
    except Exception:
        logger.exception("Job reaper pass failed")
    finally:
        db.close()
        engine.dispose()


class ViaWorker(Worker):
    """RQ worker that also runs the job reaper as part of its maintenance tasks.

    The reaper runs in the worker's main loop, never in a background thread: the worker
    forks a work-horse per job, and forking while another thread holds a lock (import,
    logging, database driver) can deadlock the child. Maintenance runs at startup (which
    recovers work lost before a restart) and then every ``job_reaper_interval_seconds``
    while the worker is idle.
    """

    via_settings: Settings

    def run_maintenance_tasks(self) -> None:
        super().run_maintenance_tasks()
        reap_once(self.via_settings, RQJobQueue(self.connection, self.via_settings))


def make_worker(settings: Settings, redis: Redis) -> ViaWorker:
    interval = settings.job_reaper_interval_seconds
    worker = ViaWorker(
        [Queue(settings.import_queue_name, connection=redis)],
        connection=redis,
        maintenance_interval=interval,
        # RQ waits up to worker_ttl - 15 s for a job before looping, so this bounds how
        # long an idle worker goes without running maintenance.
        worker_ttl=max(interval + 15, 35),
    )
    worker.via_settings = settings
    return worker
