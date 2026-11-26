"""RQ job entry points and the failure callback (without a live worker)."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.integration.conftest import register
from via_api import jobs
from via_api.storage import LocalStorage

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_bytes()


@pytest.fixture
def pending_revision(client, job_queue):
    job_queue.run = False  # leave the revision pending, as if waiting for a worker
    register(client, "jobs@example.com")
    project = client.post("/api/v1/projects", json={"name": "Jobs"}).json()
    resp = client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("board.kicad_pcb", REF, "application/octet-stream")},
    )
    return resp.json()["revision"]["id"]


@pytest.fixture
def job_env(monkeypatch, db, settings):
    """Point the job entry points at the test session and storage."""
    monkeypatch.setattr(jobs, "_session", lambda _settings: (db, SimpleNamespace(dispose=lambda: None)))
    monkeypatch.setattr(jobs, "get_storage", lambda: LocalStorage(settings.local_storage_path))
    monkeypatch.setattr(jobs, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "close", lambda: None)  # the test fixture owns the session


def test_import_revision_job_parses_the_upload(client, pending_revision, job_env):
    assert jobs.import_revision(pending_revision) == "ready"
    assert client.get(f"/api/v1/revisions/{pending_revision}").json()["object_counts"]["net_count"] == 3


def test_import_job_for_a_deleted_revision_is_a_no_op(job_env):
    assert jobs.import_revision(str(uuid.uuid4())) == "missing"


def test_failure_callback_never_leaves_revisions_processing(client, pending_revision, job_env):
    job = SimpleNamespace(args=[pending_revision])
    jobs.on_import_failure(job, None, TimeoutError, TimeoutError("job timeout"), None)
    rev = client.get(f"/api/v1/revisions/{pending_revision}").json()
    assert rev["status"] == "failed"
    assert rev["error_code"] == "processing_failed"
    assert "Try uploading" in rev["error_message"]


def test_failure_callback_leaves_finished_revisions_alone(client, pending_revision, job_env):
    jobs.import_revision(pending_revision)
    jobs.on_import_failure(SimpleNamespace(args=[pending_revision]), None, RuntimeError, RuntimeError(), None)
    assert client.get(f"/api/v1/revisions/{pending_revision}").json()["status"] == "ready"


def test_rq_queue_enqueues_with_timeout_and_callback(settings, test_redis):
    queue = jobs.RQJobQueue(test_redis, settings)
    rid = uuid.uuid4()
    queue.enqueue_import(rid)
    job = queue.queue.fetch_job(f"import-{rid}-a1")
    assert job.func_name == "via_api.jobs.import_revision"
    assert list(job.args) == [str(rid), 1]
    assert job.timeout == settings.parser_timeout_seconds + 120
    assert job.failure_callback is jobs.on_import_failure  # resolved from the stored dotted path
