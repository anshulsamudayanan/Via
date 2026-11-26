"""Analysis runs and findings through the API, with the real worker logic running inline."""

from __future__ import annotations

import gzip
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.integration.conftest import register
from via_api import jobs
from via_api.models import AnalysisRun, DesignFile, PCBGeometry
from via_api.models.base import utcnow
from via_api.models.enums import AnalysisStatus
from via_api.storage import LocalStorage

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_text()
# Removing the right-hand Edge.Cuts line opens the outline (unjoined endpoints (150,100) and (150,130)).
RIGHT_EDGE = """	(gr_line
		(start 150 100)
		(end 150 130)
		(stroke (width 0.05) (type default))
		(layer "Edge.Cuts")
		(uuid "a1f0b6a4-0000-4000-8000-0000000000a2")
	)
"""


def without_r1_pad2_net(text: str) -> str:
    start = text.index('(pad "2"', text.index('(property "Reference" "R1"'))
    end = text.index("(uuid", start)
    block = text[start:end]
    net = block[block.index("(net ") : block.index(")", block.index("(net ")) + 1]
    return text[:start] + block.replace(net, "") + text[end:]


BROKEN = without_r1_pad2_net(REF.replace(RIGHT_EDGE, ""))  # open outline + R1 pad 2 without net
OUTLINE_FIXED = without_r1_pad2_net(REF)  # still R1 pad 2 without net


def upload(client, project_id, text, name="board.kicad_pcb", design_id=None):
    data = {"project_id": project_id, **({"design_id": design_id} if design_id else {})}
    resp = client.post(
        "/api/v1/pcb/import", data=data, files={"file": (name, text.encode(), "application/octet-stream")}
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


@pytest.fixture
def broken(client):
    register(client, "analyst@example.com", "Analyst")
    project = client.post("/api/v1/projects", json={"name": "Analysis"}).json()
    imported = upload(client, project["id"], BROKEN)
    assert imported["revision"]["status"] in {"pending", "processing", "ready"}
    return project, imported["design"], imported["revision"]


def start(client, design_id, **body):
    return client.post(f"/api/v1/designs/{design_id}/analysis-runs", json=body)


def findings(client, run_id, **params):
    resp = client.get(f"/api/v1/analysis-runs/{run_id}/findings", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_run_analysis_end_to_end(client, broken):
    _, design, revision = broken
    resp = start(client, design["id"])
    assert resp.status_code == 202, resp.text
    run = client.get(f"/api/v1/analysis-runs/{resp.json()['id']}").json()
    assert run["status"] == "succeeded"
    assert run["revision_id"] == revision["id"] and run["revision_number"] == 1
    assert run["analysis_version"] and run["engine_version"]
    assert run["design_schema_version"] == "1.1.0" and run["design_parser_version"]
    assert {c["check_id"]: c["status"] for c in run["checks"]} == {
        "board_outline": "ok", "design_rules_source": "ok", "pads_without_net": "ok", "import_warnings": "ok",
        "kicad_drc": "skipped",  # no KiCad service in this test (see test_kicad_drc_pipeline.py)
    }  # fmt: skip
    assert all(c["version"] for c in run["checks"])
    assert run["summary"]["finding_count"] == 3
    assert run["summary"]["by_severity"] == {"critical": 0, "high": 1, "medium": 0, "low": 1, "info": 1}

    page = findings(client, run["id"])
    assert [(f["rule"], f["severity"]) for f in page["items"]] == [
        ("outline_open", "high"), ("copper_pad_no_net", "low"), ("project_rules_missing", "info"),
    ]  # fmt: skip
    assert page["facets"]["severity"] == {"high": 1, "low": 1, "info": 1}
    outline = page["items"][0]
    assert outline["source"] == "via_deterministic" and outline["verification"] == "verified"
    assert sorted((p["x"], p["y"]) for p in outline["region"]["points"]) == [(150.0, 100.0), (150.0, 130.0)]

    detail = client.get(f"/api/v1/findings/{outline['id']}").json()
    assert {e["label"]: e["numeric_value"] for e in detail["evidence"]}["Unjoined outline endpoints"] == 2
    assert detail["history"] == []
    pad = page["items"][1]
    assert pad["components"] == ["R1"] and [o["kind"] for o in pad["objects"]] == ["component", "pad"]


def test_filters_search_and_sort(client, broken):
    _, design, _ = broken
    run_id = start(client, design["id"]).json()["id"]
    assert [f["rule"] for f in findings(client, run_id, severity="high,low")["items"]] == [
        "outline_open",
        "copper_pad_no_net",
    ]
    assert [f["rule"] for f in findings(client, run_id, category="connectivity")["items"]] == ["copper_pad_no_net"]
    assert [f["rule"] for f in findings(client, run_id, component="R1")["items"]] == ["copper_pad_no_net"]
    assert findings(client, run_id, component="R99")["total"] == 0
    assert [f["rule"] for f in findings(client, run_id, q="outline")["items"]] == ["outline_open"]
    assert [f["rule"] for f in findings(client, run_id, q="r1")["items"]] == ["copper_pad_no_net"]  # component search
    assert findings(client, run_id, q="100%_")["total"] == 0  # LIKE metacharacters are literal
    assert [f["rule"] for f in findings(client, run_id, check_id="board_outline")["items"]] == ["outline_open"]
    assert [f["severity"] for f in findings(client, run_id, sort="severity", order="desc")["items"]] == [
        "info",
        "low",
        "high",
    ]
    page = findings(client, run_id, limit=1, offset=1)
    assert page["total"] == 3 and len(page["items"]) == 1
    bad = client.get(f"/api/v1/analysis-runs/{run_id}/findings", params={"severity": "catastrophic"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_filter"


def test_review_dismiss_reopen_with_history(client, broken):
    _, design, _ = broken
    run_id = start(client, design["id"]).json()["id"]
    pad = findings(client, run_id, check_id="pads_without_net")["items"][0]
    url = f"/api/v1/findings/{pad['id']}/review"
    no_reason = client.post(url, json={"status": "dismissed"})
    assert no_reason.status_code == 422 and no_reason.json()["error"]["code"] == "reason_required"
    dismissed = client.post(url, json={"status": "dismissed", "reason": "Unused pin, intentionally unconnected"}).json()
    assert dismissed["status"] == "dismissed" and dismissed["status_reason"].startswith("Unused pin")
    reopened = client.post(url, json={"status": "open"}).json()
    reviewed = client.post(url, json={"status": "reviewed", "reason": "Checked against schematic"}).json()
    assert reopened["status"] == "open" and reviewed["status"] == "reviewed"
    assert [(h["from_status"], h["to_status"]) for h in reviewed["history"]] == [
        ("open", "dismissed"), ("dismissed", "open"), ("open", "reviewed"),
    ]  # fmt: skip
    assert all(h["actor"]["display_name"] == "Analyst" and not h["carried_over"] for h in reviewed["history"])
    assert findings(client, run_id, status="reviewed")["total"] == 1
    assert findings(client, run_id)["facets"]["status"] == {"open": 2, "reviewed": 1}


def test_new_revision_carries_reviews_over_and_compares(client, broken):
    project, design, _ = broken
    run1 = start(client, design["id"]).json()["id"]
    pad1 = findings(client, run1, check_id="pads_without_net")["items"][0]
    client.post(f"/api/v1/findings/{pad1['id']}/review", json={"status": "dismissed", "reason": "Unused pin"})

    # Revision 2 fixes the outline; R1 pad 2 still has no net.
    upload(client, project["id"], OUTLINE_FIXED, name="board_v2.kicad_pcb", design_id=design["id"])
    run2 = start(client, design["id"]).json()
    assert run2["revision_number"] == 2
    page = findings(client, run2["id"])
    assert [f["rule"] for f in page["items"]] == ["copper_pad_no_net", "project_rules_missing"]
    pad2 = page["items"][0]
    assert pad2["fingerprint"] == pad1["fingerprint"] and pad2["id"] != pad1["id"]
    assert (pad2["status"], pad2["status_reason"], pad2["inherited"]) == ("dismissed", "Unused pin", True)
    (event,) = client.get(f"/api/v1/findings/{pad2['id']}").json()["history"]
    assert event["carried_over"] and event["actor"] is None and "revision 1" in event["reason"]

    diff = client.get(
        f"/api/v1/designs/{design['id']}/analysis-compare", params={"base_run_id": run1, "target_run_id": run2["id"]}
    ).json()
    assert [f["rule"] for f in diff["resolved"]] == ["outline_open"]
    assert [f["rule"] for f in diff["persisting"]] == ["copper_pad_no_net", "project_rules_missing"]
    assert diff["new"] == []
    # Run 1 is untouched history.
    assert findings(client, run1)["total"] == 3
    assert client.get(f"/api/v1/designs/{design['id']}/analysis-runs").json()["total"] == 2


def test_start_is_idempotent_while_queued(client, broken, job_queue):
    _, design, _ = broken
    job_queue.run = False
    first = start(client, design["id"])
    again = start(client, design["id"])
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"] and again.json()["status"] == "queued"
    other = start(client, design["id"], checks=["board_outline"])
    assert other.status_code == 202 and other.json()["id"] != first.json()["id"]
    assert other.json()["config"] == {"checks": ["board_outline"]}
    assert len(job_queue.analyses) == 2


def test_selected_checks_only(client, broken):
    _, design, _ = broken
    run = start(client, design["id"], checks=["board_outline"]).json()
    run = client.get(f"/api/v1/analysis-runs/{run['id']}").json()
    assert [c["check_id"] for c in run["checks"]] == ["board_outline"]
    assert [f["rule"] for f in findings(client, run["id"])["items"]] == ["outline_open"]


def test_unknown_check_and_unparsed_revision(client, broken, job_queue):
    project, design, _ = broken
    resp = start(client, design["id"], checks=["telepathy"])
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "unknown_check"
    job_queue.run = False
    pending = upload(client, project["id"], REF, name="pending.kicad_pcb")
    resp = start(client, pending["design"]["id"])
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_parsed"


def test_queue_failure_marks_the_run_failed(client, broken, job_queue, db):
    _, design, _ = broken
    job_queue.fail = True
    resp = start(client, design["id"])
    assert resp.status_code == 503
    run = db.scalars(select(AnalysisRun).where(AnalysisRun.kind == "pcb_analysis")).one()
    assert (run.status, run.error_code) == (AnalysisStatus.FAILED, "queue_unavailable")


def test_viewers_read_but_cannot_start_or_review(client, make_client, broken):
    project, design, _ = broken
    run_id = start(client, design["id"]).json()["id"]
    viewer = make_client()
    register(viewer, "viewer@example.com")
    client.post(f"/api/v1/projects/{project['id']}/members", json={"email": "viewer@example.com", "role": "viewer"})
    assert viewer.get(f"/api/v1/analysis-runs/{run_id}").status_code == 200
    finding_id = findings(viewer, run_id)["items"][0]["id"]
    assert start(viewer, design["id"]).status_code == 403
    review = viewer.post(f"/api/v1/findings/{finding_id}/review", json={"status": "reviewed"})
    assert review.status_code == 403


def test_archived_projects_reject_new_analyses(client, broken):
    project, design, _ = broken
    client.post(f"/api/v1/projects/{project['id']}/archive")
    resp = start(client, design["id"])
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "project_archived"


def test_designs_parsed_with_an_older_schema_are_reimported(client, broken, db, settings):
    _, design, revision = broken
    geometry = db.scalar(select(PCBGeometry).where(PCBGeometry.revision_id == uuid.UUID(revision["id"])))
    file = db.get(DesignFile, geometry.normalized_file_id)
    storage = LocalStorage(settings.local_storage_path)
    doc = json.loads(gzip.decompress(storage.get(file.storage_key)))
    doc["schema_version"] = "1.0.0"  # as stored before Stage 2
    storage.put(file.storage_key, gzip.compress(json.dumps(doc).encode()), content_type="application/gzip")
    run = client.get(f"/api/v1/analysis-runs/{start(client, design['id']).json()['id']}").json()
    assert run["status"] == "succeeded" and run["design_schema_version"] == "1.1.0"
    restored = json.loads(gzip.decompress(storage.get(file.storage_key)))
    assert restored["schema_version"] == "1.1.0"


def test_compare_rejects_runs_of_other_designs(client, broken):
    project, design, _ = broken
    run_a = start(client, design["id"]).json()["id"]
    other = upload(client, project["id"], OUTLINE_FIXED, name="other.kicad_pcb")
    run_b = start(client, other["design"]["id"]).json()["id"]
    resp = client.get(
        f"/api/v1/designs/{design['id']}/analysis-compare", params={"base_run_id": run_a, "target_run_id": run_b}
    )
    assert resp.status_code == 404


def test_checks_catalog(client, broken):
    checks = client.get("/api/v1/analysis/checks").json()
    assert {c["id"] for c in checks} >= {"board_outline", "design_rules_source", "pads_without_net", "import_warnings"}
    assert all(c["version"] for c in checks)
    assert {c["id"]: c["source"] for c in checks}["kicad_drc"] == "kicad_drc"
    assert {c["source"] for c in checks if c["id"] != "kicad_drc"} == {"via_deterministic"}


# --- Recovery -------------------------------------------------------------------------------


def test_stale_analysis_is_requeued_then_failed(client, broken, job_queue, db, settings):
    _, design, _ = broken
    job_queue.run = False
    run_id = uuid.UUID(start(client, design["id"]).json()["id"])
    run = db.get(AnalysisRun, run_id)
    for attempt in range(1, settings.job_max_attempts + 1):
        run.status = AnalysisStatus.RUNNING
        run.attempt = attempt
        run.started_at = run.heartbeat_at = utcnow() - timedelta(seconds=settings.job_stale_after_seconds + 5)
        db.commit()
        report = jobs.reap_analyses(db, job_queue, settings)
        if attempt < settings.job_max_attempts:
            assert report.requeued == [run_id] and job_queue.analyses[-1] == (run_id, attempt + 1)
            assert db.get(AnalysisRun, run_id).status == AnalysisStatus.QUEUED
    assert (run.status, run.error_code) == (AnalysisStatus.FAILED, "worker_lost")


def test_lost_queued_analysis_is_requeued(client, broken, job_queue, db, settings):
    _, design, _ = broken
    job_queue.run = False
    run_id = uuid.UUID(start(client, design["id"]).json()["id"])
    later = utcnow() + timedelta(seconds=settings.job_lost_after_seconds + 5)
    job_queue.alive.add(f"analysis-{run_id}-a1")
    assert jobs.reap_analyses(db, job_queue, settings, now=later).requeued == []
    job_queue.alive.clear()
    assert jobs.reap_analyses(db, job_queue, settings, now=later).requeued == [run_id]


def test_rq_enqueues_analysis_jobs(settings, test_redis):
    queue = jobs.RQJobQueue(test_redis, settings)
    rid = uuid.uuid4()
    queue.enqueue_analysis(rid)
    job = queue.queue.fetch_job(f"analysis-{rid}-a1")
    assert job.func_name == "via_api.jobs.analyze_run" and list(job.args) == [str(rid), 1]
    assert job.failure_callback is jobs.on_analysis_failure
