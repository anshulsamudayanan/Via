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


#: The checks these framework tests were written against; later checks have their own tests
#: (test_connectivity_and_manufacturing.py, test_kicad_drc_mapping.py, ...).
FRAMEWORK_CHECKS = ["board_outline", "design_rules_source", "import_warnings", "kicad_drc", "pads_without_net"]


def start(client, design_id, **body):
    body.setdefault("checks", FRAMEWORK_CHECKS)
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
    assert other.json()["config"]["checks"] == ["board_outline"]
    assert other.json()["config"]["options"]["manufacturing_profile"]["key"] == "via-conservative"  # snapshot
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


def test_dashboard_summary_and_latest_work(client, make_client, broken):
    """The dashboard's counts and per-project status come from real rows, scoped to access."""
    project, design, revision = broken
    before = client.get(f"/api/v1/projects/{project['id']}").json()
    assert before["latest_import"] == {
        "design_id": design["id"], "design_name": design["name"], "revision_number": 1,
        "status": "ready", "at": before["latest_import"]["at"],
    }  # fmt: skip
    assert before["latest_analysis"] is None
    summary = client.get("/api/v1/projects/summary").json()
    assert summary == {"active": 1, "archived": 0, "designs": 1, "imports_7d": 1, "analyses_7d": 0}

    run_id = start(client, design["id"]).json()["id"]
    listed = client.get("/api/v1/projects").json()["items"][0]
    assert listed["latest_analysis"]["status"] == "succeeded"
    assert listed["latest_analysis"]["finding_count"] == 3
    by_sev = listed["latest_analysis"]["by_severity"]
    assert sum(by_sev.values()) == 3 and by_sev["high"] == 1
    assert listed["latest_analysis"]["design_id"] == design["id"]
    assert client.get("/api/v1/projects/summary").json()["analyses_7d"] == 1
    assert client.get(f"/api/v1/analysis-runs/{run_id}").json()["revision_id"] == revision["id"]

    # Another user sees none of it.
    other = make_client()
    register(other, "outsider@example.com", "Outsider")
    assert other.get("/api/v1/projects/summary").json() == {
        "active": 0, "archived": 0, "designs": 0, "imports_7d": 0, "analyses_7d": 0,
    }  # fmt: skip

    # Archived projects drop out of the active counts.
    client.post(f"/api/v1/projects/{project['id']}/archive")
    assert client.get("/api/v1/projects/summary").json() == {
        "active": 0, "archived": 1, "designs": 0, "imports_7d": 0, "analyses_7d": 0,
    }  # fmt: skip


def test_browse_designs_across_projects(client, make_client, broken):
    """GET /designs/browse lists designs from every accessible project, with filters, and nothing else."""
    project, design, revision = broken
    other_project = client.post("/api/v1/projects", json={"name": "Second board"}).json()
    upload(client, other_project["id"], REF, name="power_stage.kicad_pcb")
    start(client, design["id"])

    page = client.get("/api/v1/designs/browse").json()
    assert page["total"] == 2
    by_name = {item["name"]: item for item in page["items"]}
    first = by_name[design["name"]]
    assert first["project"] == {"id": project["id"], "name": project["name"]}
    assert first["my_role"] == "owner" and first["revision_count"] == 1
    assert first["current_revision"]["id"] == revision["id"]
    assert first["latest_revision"]["status"] == "ready"
    assert first["latest_revision"]["object_counts"]["component_count"] > 0
    assert first["latest_analysis"]["status"] == "succeeded"
    assert first["latest_analysis"]["finding_count"] == 3 and first["latest_analysis"]["revision_number"] == 1
    assert by_name["power_stage"]["latest_analysis"] is None

    assert [i["name"] for i in client.get("/api/v1/designs/browse?q=second").json()["items"]] == ["power_stage"]
    assert client.get("/api/v1/designs/browse?q=100%25").json()["total"] == 0  # LIKE wildcards are literal
    assert client.get(f"/api/v1/designs/browse?project_id={project['id']}").json()["total"] == 1
    assert client.get("/api/v1/designs/browse?status=failed").json()["total"] == 0
    assert client.get("/api/v1/designs/browse?status=ready").json()["total"] == 2
    names = [i["name"] for i in client.get("/api/v1/designs/browse?sort=name").json()["items"]]
    assert names == sorted(names, key=str.lower)
    assert client.get("/api/v1/designs/browse?status=bogus").status_code == 422

    # Archived projects are hidden unless asked for.
    client.post(f"/api/v1/projects/{other_project['id']}/archive")
    assert client.get("/api/v1/designs/browse").json()["total"] == 1
    archived = client.get("/api/v1/designs/browse?include_archived=true").json()
    assert archived["total"] == 2
    assert {i["name"]: i["project_archived"] for i in archived["items"]}["power_stage"] is True

    # Other users see nothing, and can't probe someone else's project id.
    outsider = make_client()
    register(outsider, "browser-outsider@example.com", "Outsider")
    assert outsider.get("/api/v1/designs/browse?include_archived=true").json()["total"] == 0
    assert outsider.get(f"/api/v1/designs/browse?project_id={project['id']}").status_code == 404


def test_cross_project_analysis_views(client, make_client, broken):
    """GET /analysis/runs and /analysis/findings span projects, use each design's latest run, and stay scoped."""
    project, design, _ = broken
    first = start(client, design["id"]).json()["id"]
    other = client.post("/api/v1/projects", json={"name": "Clean board"}).json()
    clean = upload(client, other["id"], REF, name="clean.kicad_pcb")
    start(client, clean["design"]["id"])

    runs = client.get("/api/v1/analysis/runs").json()
    assert runs["total"] == 2
    item = next(r for r in runs["items"] if r["id"] == first)
    assert item["design"] == {"id": design["id"], "name": design["name"]}
    assert item["project"]["id"] == project["id"] and item["revision_number"] == 1
    assert item["status"] == "succeeded" and item["finding_count"] == 3 and item["by_severity"]["high"] == 1
    assert client.get("/api/v1/analysis/runs?status=failed").json()["total"] == 0
    assert client.get(f"/api/v1/analysis/runs?project_id={other['id']}").json()["total"] == 1

    findings = client.get("/api/v1/analysis/findings").json()
    assert findings["designs_analysed"] == 2
    broken_rules = {f["rule"] for f in findings["items"] if f["design"]["id"] == design["id"]}
    assert {"outline_open", "copper_pad_no_net"} <= broken_rules
    assert findings["items"][0]["severity"] == "high"  # most severe first
    assert findings["by_severity"]["high"] == 1
    high = client.get("/api/v1/analysis/findings?severity=high").json()
    assert [f["rule"] for f in high["items"]] == ["outline_open"]
    assert high["by_severity"] == findings["by_severity"]  # facets ignore the severity filter
    assert client.get("/api/v1/analysis/findings?q=R1").json()["items"][0]["rule"] == "copper_pad_no_net"
    assert client.get("/api/v1/analysis/findings?q=outline").json()["total"] == 1

    # Dismissing a finding moves it out of the default (open) view.
    target = high["items"][0]["id"]
    assert (
        client.post(f"/api/v1/findings/{target}/review", json={"status": "dismissed", "reason": "known"}).status_code
        == 200
    )
    assert client.get("/api/v1/analysis/findings?severity=high").json()["total"] == 0
    assert client.get("/api/v1/analysis/findings?severity=high&status=all").json()["total"] == 1

    # A newer analysis replaces the older one in the findings view.
    fixed = upload(client, project["id"], OUTLINE_FIXED, design_id=design["id"])
    start(client, design["id"], revision_id=fixed["revision"]["id"])
    current = client.get("/api/v1/analysis/findings?status=all").json()
    assert {f["revision_number"] for f in current["items"] if f["design"]["id"] == design["id"]} == {2}
    assert "outline_open" not in {f["rule"] for f in current["items"]}

    outsider = make_client()
    register(outsider, "analysis-outsider@example.com", "Outsider")
    assert outsider.get("/api/v1/analysis/runs").json()["total"] == 0
    assert outsider.get("/api/v1/analysis/findings").json() == {
        "items": [], "total": 0, "limit": 25, "offset": 0, "by_severity": {}, "designs_analysed": 0,
    }  # fmt: skip
    assert outsider.get(f"/api/v1/analysis/findings?project_id={project['id']}").status_code == 404


def test_cross_project_parts(client, make_client, broken):
    """GET /components/parts groups the current revision's components by value and footprint, across projects."""
    project, design, _ = broken
    other = client.post("/api/v1/projects", json={"name": "Second"}).json()
    upload(client, other["id"], REF, name="copy.kicad_pcb")

    parts = client.get("/api/v1/components/parts").json()
    assert parts["designs"] == 2 and parts["placements"] > 0
    assert sum(p["placements"] for p in parts["items"]) == parts["placements"]
    assert all(p["design_count"] == 2 for p in parts["items"])  # same board in both projects
    r1 = next(p for p in parts["items"] if "R1" in p["references"])
    assert {d["name"] for d in r1["designs"]} == {design["name"], "copy"}
    assert client.get(f"/api/v1/components/parts?project_id={project['id']}").json()["designs"] == 1

    found = client.get("/api/v1/components/parts?q=R1").json()
    assert found["total"] >= 1 and all(any(r.startswith("R1") for r in p["references"]) for p in found["items"])
    by_value = [p["value"] for p in client.get("/api/v1/components/parts?sort=value").json()["items"]]
    assert by_value == sorted(by_value, key=lambda v: (v is None, (v or "").lower()))

    # Only the current revision counts: a new revision that drops the net doesn't double the placements.
    upload(client, project["id"], OUTLINE_FIXED, design_id=design["id"])
    assert client.get("/api/v1/components/parts").json()["placements"] == parts["placements"]

    client.post(f"/api/v1/projects/{other['id']}/archive")
    assert client.get("/api/v1/components/parts").json()["designs"] == 1
    assert client.get("/api/v1/components/parts?include_archived=true").json()["designs"] == 2

    outsider = make_client()
    register(outsider, "parts-outsider@example.com", "Outsider")
    assert outsider.get("/api/v1/components/parts?include_archived=true").json()["total"] == 0
    assert outsider.get(f"/api/v1/components/parts?project_id={project['id']}").status_code == 404
