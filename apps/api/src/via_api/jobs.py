"""Background job queue (RQ on Redis) and job entry points.

The API enqueues; the worker (``via-api worker``) runs jobs in a forked
process per job. Each job builds its own database session and storage client
from settings. The parser itself runs in a further, credential-free sandbox
subprocess (see ``parsing/sandbox.py``).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from redis import Redis
from rq import Callback, Queue
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from via_api.config import Settings, get_settings
from via_api.models import DesignRevision
from via_api.models.enums import RevisionStatus
from via_api.parsing.importer import mark_failed, process_revision
from via_api.parsing.sandbox import SandboxLimits
from via_api.storage import get_storage

logger = logging.getLogger("via_api.jobs")


class JobQueue(Protocol):
    def enqueue_import(self, revision_id: uuid.UUID) -> None: ...


class RQJobQueue:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self.queue = Queue(settings.import_queue_name, connection=redis)
        # The job outlives the parser's own timeout (download + persist time).
        self.job_timeout = settings.parser_timeout_seconds + 120

    def enqueue_import(self, revision_id: uuid.UUID) -> None:
        self.queue.enqueue(
            "via_api.jobs.import_revision",
            str(revision_id),
            job_timeout=self.job_timeout,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            on_failure=Callback("via_api.jobs.on_import_failure", timeout=60),
            job_id=f"import-{revision_id}",
        )


def sandbox_limits(settings: Settings) -> SandboxLimits:
    return SandboxLimits(
        timeout_seconds=settings.parser_timeout_seconds,
        memory_bytes=settings.parser_memory_limit_mb * 1024 * 1024,
    )


def _session(settings: Settings) -> tuple[Session, Any]:
    engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"})
    return Session(bind=engine, expire_on_commit=False), engine


def import_revision(revision_id: str) -> str:
    """RQ job: parse and persist one uploaded revision."""
    settings = get_settings()
    db, engine = _session(settings)
    try:
        revision = process_revision(db, get_storage(), uuid.UUID(revision_id), sandbox_limits(settings))
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
        if revision is not None and revision.status in (RevisionStatus.PENDING, RevisionStatus.PROCESSING):
            logger.error("Import job for %s failed: %s", revision.id, type.__name__ if type else "unknown")
            mark_failed(
                db, revision, "processing_failed", "Processing stopped unexpectedly. Try uploading the file again."
            )
            db.commit()
    finally:
        db.close()
        engine.dispose()
