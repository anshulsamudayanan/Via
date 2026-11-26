# ruff: noqa: E501  (test setup)
"""Concurrency: simultaneous applies, rollbacks and revision allocation on one design.

These need committed data and separate database connections (the normal test session is one
rolled-back transaction), so they use their own app and session factory and clean up afterwards.
Each thread opens its own session and holds its locks a little while before committing, so the
race window is real rather than hoped for.
"""

from __future__ import annotations

import threading
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from tests.engineering.synthetic import Board
from tests.integration.conftest import register
from via_api.db import get_db
from via_api.deps import get_job_queue
from via_api.errors import APIError
from via_api.models import ChangeSet, DesignRevision, User
from via_api.models.enums import ChangeSetStatus, RevisionStatus
from via_api.parsing.importer import process_revision
from via_api.parsing.sandbox import SandboxLimits
from via_api.services import changes as change_svc
from via_api.services import designs as design_svc
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext
from via_api.storage import LocalStorage


class CommittedQueue:
    """Imports run inline in their own committed session; exports are only recorded."""

    def __init__(self, factory, storage_root) -> None:
        self.factory, self.storage_root = factory, storage_root
        self.exports: list[uuid.UUID] = []

    def enqueue_import(self, revision_id, attempt=1):
        with self.factory() as s:
            process_revision(
                s, LocalStorage(self.storage_root), revision_id, SandboxLimits(timeout_seconds=30, memory_bytes=1024**3)
            )

    def enqueue_analysis(self, run_id, attempt=1):
        pass

    def enqueue_optimization(self, run_id, attempt=1):
        pass

    def enqueue_export(self, run_id, attempt=1):
        self.exports.append(run_id)

    def job_alive(self, job_id):
        return True


@pytest.fixture
def live(migrated_engine, settings, test_redis, mailer):
    from via_api.config import get_settings
    from via_api.deps import get_email_sender
    from via_api.main import create_app
    from via_api.redis_client import get_redis
    from via_api.storage import get_storage

    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    queue = CommittedQueue(factory, settings.local_storage_path)
    app = create_app(settings)

    def db_dep():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_redis] = lambda: test_redis
    app.dependency_overrides[get_storage] = lambda: LocalStorage(settings.local_storage_path)
    app.dependency_overrides[get_email_sender] = lambda: mailer
    app.dependency_overrides[get_job_queue] = lambda: queue
    email = f"race-{uuid.uuid4().hex[:8]}@example.com"
    with TestClient(app, headers={"X-VIA-Request": "1"}) as c:
        me = register(c, email)
        project = c.post("/api/v1/projects", json={"name": "Races"}).json()
        b = Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}])
        b.track((5, 5), (15, 5), 0.1, "A")
        imported = c.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                          files={"file": ("s.kicad_pcb", b.bytes(), "application/octet-stream")}).json()  # fmt: skip
        assert imported["revision"]["status"] == "ready", imported
        norm = c.get(f"/api/v1/pcb/{imported['design']['id']}/normalized").json()
        yield SimpleNamespace(client=c, factory=factory, queue=queue, user_id=uuid.UUID(me["user"]["id"]),
                              design_id=uuid.UUID(imported["design"]["id"]), components=norm["components"])  # fmt: skip
    with migrated_engine.begin() as conn:
        u = me["user"]["id"]
        conn.execute(text("DELETE FROM projects WHERE owner_id = :u"), {"u": u})
        conn.execute(
            text(
                "DELETE FROM organizations WHERE id IN (SELECT organization_id FROM organization_memberships WHERE user_id = :u)"
            ),
            {"u": u},
        )
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": u})


def race(n: int, work) -> list[object]:
    """Run ``work(i)`` in ``n`` threads started together; return each result or exception."""
    barrier = threading.Barrier(n)
    results: list[object] = [None] * n

    def run(i: int) -> None:
        barrier.wait()
        try:
            results[i] = work(i)
        except Exception as exc:
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return results


def move(live, ref: str, dx: float) -> dict:
    comp = next(c for c in live.components if c["reference"] == ref)
    return {"kind": "move_component", "target": {"kind": "component", "id": comp["id"], "label": ref},
            "after": {"x": comp["position"]["x"] + dx, "y": comp["position"]["y"]}}  # fmt: skip


def apply_in_thread(live, change_set_id: uuid.UUID, hold: float = 0.3):
    with live.factory() as s:
        ctx = AuthContext(user=s.get(User, live.user_id), session=None)
        cs = s.get(ChangeSet, change_set_id)
        run = change_svc.request_apply(s, ctx, cs, ClientInfo())
        time.sleep(hold)  # keep the locks while the other thread tries
        s.commit()
        return run.id


def test_revision_numbers_never_collide(live):
    def allocate(i: int) -> int:
        with live.factory() as s:
            n = design_svc.next_revision_number(s, live.design_id)
            s.add(DesignRevision(design_id=live.design_id, project_id=s.scalar(select(DesignRevision.project_id).limit(1)),
                                 revision_number=n, status=RevisionStatus.FAILED, source_format="kicad", source_sha256=f"{i:064d}"))  # fmt: skip
            time.sleep(0.1)
            s.commit()
            return n

    results = race(5, allocate)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sorted(results) == [2, 3, 4, 5, 6], results  # revision 1 is the upload


def test_the_same_change_set_is_applied_once(live):
    cs = live.client.post(
        f"/api/v1/designs/{live.design_id}/change-sets", json={"changes": [move(live, "R1", 1)]}
    ).json()
    results = race(3, lambda i: apply_in_thread(live, uuid.UUID(cs["id"])))
    ok = [r for r in results if isinstance(r, uuid.UUID)]
    refused = [r for r in results if isinstance(r, APIError)]
    assert len(ok) == 1 and len(refused) == 2, results
    assert all(r.status_code == 409 for r in refused)
    with live.factory() as s:
        assert s.get(ChangeSet, uuid.UUID(cs["id"])).status == ChangeSetStatus.APPLYING


def test_two_change_sets_on_one_design_are_serialized(live):
    url = f"/api/v1/designs/{live.design_id}/change-sets"
    a = live.client.post(url, json={"changes": [move(live, "R1", 1)]}).json()
    b = live.client.post(url, json={"changes": [move(live, "R2", 1)]}).json()
    results = race(2, lambda i: apply_in_thread(live, uuid.UUID((a, b)[i]["id"])))
    errors = [r for r in results if isinstance(r, APIError)]
    assert len(errors) == 1 and errors[0].code == "apply_in_progress", results


def test_export_refuses_a_base_that_stopped_being_current(live, settings):
    """If the design moved on between apply and the worker, the export fails instead of forking history."""
    url = f"/api/v1/designs/{live.design_id}/change-sets"
    cs = live.client.post(url, json={"changes": [move(live, "R1", 1)]}).json()
    assert live.client.post(f"/api/v1/change-sets/{cs['id']}/apply").status_code == 202
    with live.factory() as s:  # someone uploads/promotes another revision meanwhile
        rev = DesignRevision(design_id=live.design_id, project_id=s.get(ChangeSet, uuid.UUID(cs["id"])).project_id,
                             revision_number=design_svc.next_revision_number(s, live.design_id), status=RevisionStatus.READY,
                             source_format="kicad", source_sha256="f" * 64)  # fmt: skip
        s.add(rev)
        s.flush()
        from via_api.models import Design

        s.get(Design, live.design_id).current_revision_id = rev.id
        s.commit()
    with live.factory() as s:
        change_svc.process_export(s, LocalStorage(settings.local_storage_path), live.queue.exports[-1],
                                  SandboxLimits(timeout_seconds=60, memory_bytes=1024**3), import_revision=lambda rid: None)  # fmt: skip
    got = live.client.get(f"/api/v1/change-sets/{cs['id']}").json()
    assert got["status"] == "failed" and got["error_code"] == "base_not_current"
