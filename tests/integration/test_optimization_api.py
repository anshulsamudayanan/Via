# ruff: noqa: E501  (test data)
"""VIA Optimize through the API with the worker logic running inline."""

from __future__ import annotations

import pytest

from tests.engineering.synthetic import Board
from tests.integration.conftest import register


def board() -> bytes:
    # Outline 0..40 x 0..30, parts only in the top-left: the outline can shrink. A 0.1 mm track is below the profile.
    b = Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}])
    b.track((5, 5), (15, 5), 0.1, "A")
    return b.bytes()


@pytest.fixture
def design(client):
    register(client, "opt@example.com")
    project = client.post("/api/v1/projects", json={"name": "Optimize"}).json()
    return client.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                       files={"file": ("s.kicad_pcb", board(), "application/octet-stream")}).json()["design"]  # fmt: skip


def start(client, design_id, **body):
    return client.post(f"/api/v1/designs/{design_id}/optimization-runs", json=body)


def test_run_generates_validated_candidates_without_touching_the_design(client, design):
    revisions_before = client.get(f"/api/v1/designs/{design['id']}").json()["revision_count"]
    resp = start(client, design["id"], objectives=["area", "manufacturability"])
    assert resp.status_code == 202, resp.text
    run = client.get(f"/api/v1/optimization-runs/{resp.json()['id']}").json()
    assert run["status"] == "succeeded" and run["optimizer_version"]
    assert run["config"]["options"]["manufacturing_profile"]["key"] == "via-conservative"
    cands = {c["key"]: c for c in client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()}
    assert set(cands) == {"outline_fit", "track_min_width"}
    assert all(c["status"] == "validated" for c in cands.values())
    detail = client.get(f"/api/v1/optimization-candidates/{cands['outline_fit']['id']}").json()
    (change,) = detail["changes"]
    assert change["kind"] == "set_outline_rect" and change["exportable"] and change["before"]["max_x"] == 40
    assert client.get(f"/api/v1/designs/{design['id']}").json()["revision_count"] == revisions_before  # never applied


def test_compare_and_pareto(client, design):
    run = start(client, design["id"], objectives=["area", "manufacturability"]).json()
    cmp_ = client.get(f"/api/v1/optimization-runs/{run['id']}/compare").json()
    assert cmp_["objectives"] == ["area", "manufacturability"]
    rows = {r["key"]: r for r in cmp_["rows"]}
    assert rows["outline_fit"]["deltas"]["board_area_mm2"] < 0
    assert rows["track_min_width"]["deltas"]["manufacturing_issues"] < 0
    # Neither beats the other on both objectives: both are on the Pareto front.
    assert len(cmp_["pareto"]) == 2


def test_decisions(client, design):
    run = start(client, design["id"], objectives=["area", "placement"]).json()
    cands = {c["key"]: c for c in client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()}
    accepted = client.post(
        f"/api/v1/optimization-candidates/{cands['outline_fit']['id']}/decision", json={"status": "accepted"}
    ).json()
    assert accepted["status"] == "accepted"
    if "placement_ratsnest" in cands:  # moves routed parts: awaiting validation, can't be accepted
        resp = client.post(
            f"/api/v1/optimization-candidates/{cands['placement_ratsnest']['id']}/decision", json={"status": "accepted"}
        )
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_validated"
    no_reason = client.post(
        f"/api/v1/optimization-candidates/{cands['outline_fit']['id']}/decision", json={"status": "rejected"}
    )
    assert no_reason.status_code == 422


def test_constraints_and_inputs_are_recorded(client, design):
    run = start(client, design["id"], objectives=["area"], constraints={"outline_fixed": True}).json()
    run = client.get(f"/api/v1/optimization-runs/{run['id']}").json()
    assert run["config"]["constraints"]["outline_fixed"] is True
    assert client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json() == []
    assert any("fixed" in n for n in run["summary"]["notes"])
    assert start(client, design["id"], objectives=["teleport"]).status_code == 422
    assert start(client, design["id"], objectives=[]).status_code == 422


def test_viewers_cannot_start_or_decide(client, make_client, design):
    project_id = client.get(f"/api/v1/designs/{design['id']}").json()["project_id"]
    viewer = make_client()
    register(viewer, "optviewer@example.com")
    client.post(f"/api/v1/projects/{project_id}/members", json={"email": "optviewer@example.com", "role": "viewer"})
    run = start(client, design["id"], objectives=["area"]).json()
    assert start(viewer, design["id"], objectives=["area"]).status_code == 403
    cand = client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()[0]
    assert viewer.get(f"/api/v1/optimization-candidates/{cand['id']}").status_code == 200
    assert (
        viewer.post(f"/api/v1/optimization-candidates/{cand['id']}/decision", json={"status": "accepted"}).status_code
        == 403
    )


def test_stale_optimization_run_is_requeued(client, design, job_queue, db, settings):
    import uuid
    from datetime import timedelta

    from via_api import jobs
    from via_api.models import AnalysisRun
    from via_api.models.base import utcnow
    from via_api.models.enums import AnalysisStatus

    job_queue.run = False
    run_id = uuid.UUID(start(client, design["id"], objectives=["area"]).json()["id"])
    run = db.get(AnalysisRun, run_id)
    run.status = AnalysisStatus.RUNNING
    run.started_at = run.heartbeat_at = utcnow() - timedelta(seconds=settings.job_stale_after_seconds + 5)
    db.commit()
    report = jobs.reap_analyses(db, job_queue, settings)
    assert report.requeued == [run_id] and job_queue.optimizations[-1] == (run_id, 2)
    assert db.get(AnalysisRun, run_id).job_id == f"optimization-{run_id}-a2"


def test_candidates_carry_the_full_record(client, design):
    run = start(client, design["id"], objectives=["area"]).json()
    run = client.get(f"/api/v1/optimization-runs/{run['id']}").json()
    assert run["summary"]["baseline"]  # the live "phase" is replaced by the final summary
    (c,) = client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()
    assert c["lifecycle"] == "validated" and len(c["candidate_hash"]) == 64
    assert c["score"] is None and c["execution"]["deterministic"] is True
    assert any("KiCad DRC" in s for s in c["limitations"])
    by_id = {r["id"]: r["status"] for r in c["constraints_evaluated"]}
    assert by_id["component_identity"] == "satisfied" and by_id["net_connectivity"] == "satisfied"
    assert by_id["component_overlap"] == "not_applicable"


def test_weights_rank_but_are_validated_against_the_objectives(client, design):
    run = start(
        client, design["id"], objectives=["area", "manufacturability"], weights={"area": 2, "manufacturability": 1}
    ).json()
    run = client.get(f"/api/v1/optimization-runs/{run['id']}").json()
    assert run["config"]["weights"] == {"area": 2.0, "manufacturability": 1.0}
    cands = {c["key"]: c for c in client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()}
    assert {c["score"]["rank"] for c in cands.values()} == {1, 2}
    assert all(c["status"] == "validated" for c in cands.values())  # weights never change validation
    assert start(client, design["id"], objectives=["area"], weights={"placement": 1}).status_code == 422
    assert start(client, design["id"], objectives=["area"], weights={"area": -1}).status_code == 422


def test_declared_requirements_block_acceptance(client, design):
    cons = {"requirements": [{"kind": "impedance_targets", "description": "50 ohm"}]}
    run = start(client, design["id"], objectives=["area"], constraints=cons).json()
    (c,) = client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()
    assert c["lifecycle"] == "needs_review" and c["validation"]["status"] == "unverified"
    assert any(
        r["id"] == "requirement:impedance_targets" and r["status"] == "unverified" for r in c["constraints_evaluated"]
    )
    resp = client.post(f"/api/v1/optimization-candidates/{c['id']}/decision", json={"status": "accepted"})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_validated"


def test_lifecycle_follows_the_decision(client, design):
    run = start(client, design["id"], objectives=["area"]).json()
    (c,) = client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()
    accepted = client.post(f"/api/v1/optimization-candidates/{c['id']}/decision", json={"status": "accepted"}).json()
    assert accepted["lifecycle"] == "accepted"


def test_module_declarations_need_a_session_and_classify_every_capability(client, make_client):
    assert make_client().get("/api/v1/optimization-modules").status_code == 401
    register(client, "modules@example.com")
    mods = {m["key"]: m for m in client.get("/api/v1/optimization-modules").json()}
    assert mods["outline_fit"]["status"] == "implemented" and "net_connectivity" in mods["outline_fit"]["preserves"]
    assert mods["bom_cost"]["status"] == "partial" and mods["component_alternates"]["status"] == "planned"
    assert mods["rerouting"]["status"] == "unsupported" and mods["area_analysis"]["status"] == "implemented"
    assert "impedance_targets" in mods["placement_ratsnest"]["cannot_evaluate"]


def test_another_user_cannot_see_runs_or_candidates(client, make_client, design):
    run = start(client, design["id"], objectives=["area"]).json()
    (c,) = client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()
    stranger = make_client()
    register(stranger, "optstranger@example.com")
    assert stranger.get(f"/api/v1/optimization-runs/{run['id']}").status_code == 404
    assert stranger.get(f"/api/v1/optimization-runs/{run['id']}/candidates").status_code == 404
    assert stranger.get(f"/api/v1/optimization-candidates/{c['id']}").status_code == 404
    assert start(stranger, design["id"], objectives=["area"]).status_code == 404


# ---- supplier pricing (Mouser) ------------------------------------------------------------------------------


class FakeSupplier:
    """Stands in for Mouser: returns the listings a test gives it, records what was asked."""

    def __init__(self, listings=None, error=None):
        self.listings, self.error, self.asked = listings or {}, error, []

    def offers(self, mpn):
        from via_api.suppliers import SupplierError

        self.asked.append(mpn)
        if self.error:
            raise SupplierError(self.error, fatal=True)
        return self.listings.get(mpn, [])


def offer(mpn, spn="S1", stock=1000, price=0.10):
    from via_opt.bom import Offer, PriceBreak

    return Offer(
        supplier="mouser",
        supplier_part_number=spn,
        mpn=mpn,
        stock=stock,
        currency="USD",
        price_breaks=[PriceBreak(quantity=1, unit_price=price)],
    )


@pytest.fixture
def priced_design(client):
    register(client, "bom@example.com")
    project = client.post("/api/v1/projects", json={"name": "BOM"}).json()
    b = Board().footprint("R1", 5, 5, [{"net": "A"}], props={"MPN": "RC-10K", "Manufacturer": "ACME"})
    b.footprint("R2", 10, 5, [{"net": "A"}], props={"MPN": "RC-10K"}).footprint(
        "C1", 15, 5, [{"net": "A"}], props={"MPN": "CAP-1U"}
    )
    b.footprint("U1", 20, 5, [{"net": "A"}])  # no part number
    d = client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("s.kicad_pcb", b.bytes(), "application/octet-stream")},
    ).json()["design"]
    return project, d


def test_pricing_needs_the_owners_consent_and_never_looks_anything_up_without_it(client, priced_design, monkeypatch):
    project, d = priced_design
    fake = FakeSupplier({"RC-10K": [offer("RC-10K")]})
    monkeypatch.setattr("via_api.services.optimizer.supplier_factory", lambda: fake)
    resp = start(client, d["id"], objectives=["cost"], build_quantity=10)
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "consent_required" and fake.asked == []
    assert client.get(f"/api/v1/projects/{project['id']}/supplier-consent").json()["granted"] is False


def test_priced_bom_uses_real_listings_for_exact_part_numbers_and_lists_the_rest(client, priced_design, monkeypatch):
    project, d = priced_design
    fake = FakeSupplier(
        {"RC-10K": [offer("RC-10K", price=0.10), offer("RC-10K-X", "WRONG", price=0.001)]}
    )  # CAP-1U: no listing
    monkeypatch.setattr("via_api.services.optimizer.supplier_factory", lambda: fake)
    assert client.put(f"/api/v1/projects/{project['id']}/supplier-consent").json()["granted"] is True
    run = start(client, d["id"], objectives=["cost"], build_quantity=10).json()
    run = client.get(f"/api/v1/optimization-runs/{run['id']}").json()
    assert run["status"] == "succeeded" and run["config"]["bom"] == {"build_quantity": 10}
    assert sorted(fake.asked) == ["CAP-1U", "RC-10K"]  # only part numbers were sent; U1 has none
    bom = run["summary"]["analysis"]["bom"]
    assert bom["status"] == "partial" and bom["lines"] == 3 and bom["lines_priced"] == 1 and bom["currency"] == "USD"
    row = bom["strategies"]["cheapest"]["lines"][0]
    assert (row["mpn"], row["needed"], row["total"], row["supplier_part_number"]) == (
        "RC-10K",
        20,
        2.0,
        "S1",
    )  # 2 per board x 10 boards x 0.10
    assert bom["strategies"]["cheapest"]["total"] == 2.0
    reasons = {u["key"]: u["reason"] for u in bom["unpriced"]}
    assert any("exact part number" in r for r in reasons.values()) and any(
        "No manufacturer part number" in r for r in reasons.values()
    )
    assert any("not a quote" in n for n in bom["notes"])


def test_without_a_build_quantity_nothing_is_looked_up(client, priced_design, monkeypatch):
    project, d = priced_design
    fake = FakeSupplier({"RC-10K": [offer("RC-10K")]})
    monkeypatch.setattr("via_api.services.optimizer.supplier_factory", lambda: fake)
    client.put(f"/api/v1/projects/{project['id']}/supplier-consent")
    run = start(client, d["id"], objectives=["cost"]).json()
    run = client.get(f"/api/v1/optimization-runs/{run['id']}").json()
    assert fake.asked == [] and "bom" not in run["summary"]["analysis"]
    assert start(client, d["id"], objectives=["cost"], build_quantity=0).status_code == 422


def test_a_supplier_failure_stops_the_lookups_and_is_reported_without_prices(client, priced_design, monkeypatch):
    project, d = priced_design
    fake = FakeSupplier(error="Mouser's rate limit was reached.")
    monkeypatch.setattr("via_api.services.optimizer.supplier_factory", lambda: fake)
    client.put(f"/api/v1/projects/{project['id']}/supplier-consent")
    run = start(client, d["id"], objectives=["cost"], build_quantity=5).json()
    bom = client.get(f"/api/v1/optimization-runs/{run['id']}").json()["summary"]["analysis"]["bom"]
    assert (
        bom["status"] == "none" and bom["strategies"] == {} and len(fake.asked) == 1
    )  # stopped after the first failure
    assert all("rate limit" in u["reason"] for u in bom["unpriced"] if "part number in the design" not in u["reason"])


def test_pricing_is_unavailable_without_a_configured_supplier(client, priced_design, monkeypatch):
    project, d = priced_design
    monkeypatch.setattr("via_api.services.optimizer.supplier_factory", lambda: None)
    client.put(f"/api/v1/projects/{project['id']}/supplier-consent")
    resp = start(client, d["id"], objectives=["cost"], build_quantity=5)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "supplier_unavailable"
    assert client.get("/api/v1/suppliers/status").json() == {"provider": "mouser", "configured": False}


def test_revoking_consent_stops_pricing_and_only_the_owner_can_change_it(
    client, make_client, priced_design, monkeypatch
):
    project, d = priced_design
    fake = FakeSupplier({"RC-10K": [offer("RC-10K")]})
    monkeypatch.setattr("via_api.services.optimizer.supplier_factory", lambda: fake)
    editor = make_client()
    register(editor, "bomeditor@example.com")
    client.post(f"/api/v1/projects/{project['id']}/members", json={"email": "bomeditor@example.com", "role": "editor"})
    assert editor.put(f"/api/v1/projects/{project['id']}/supplier-consent").status_code == 403
    client.put(f"/api/v1/projects/{project['id']}/supplier-consent")
    assert client.delete(f"/api/v1/projects/{project['id']}/supplier-consent").status_code == 204
    assert start(editor, d["id"], objectives=["cost"], build_quantity=5).status_code == 403
    stranger = make_client()
    register(stranger, "bomstranger@example.com")
    assert stranger.get(f"/api/v1/projects/{project['id']}/supplier-consent").status_code == 404
    assert stranger.put(f"/api/v1/projects/{project['id']}/supplier-consent").status_code == 404


def test_report_contains_only_calculated_numbers_and_says_what_validated_means(client, design):
    run = start(client, design["id"], objectives=["area", "manufacturability"]).json()
    rep = client.get(f"/api/v1/optimization-runs/{run['id']}/report").json()
    assert rep["run"]["id"] == run["id"] and rep["parameters"]["objectives"] == ["area", "manufacturability"]
    base = {b["metric"]: b["value"] for b in rep["baseline"]}
    assert base["board_area_mm2"] == 1200 and "cost_index" not in rep["parameters"]
    cands = {c["key"]: c for c in rep["candidates"]}
    fit = cands["outline_fit"]
    area = next(m for m in fit["metrics"] if m["metric"] == "board_area_mm2")
    assert (
        (area["before"], area["after"]) == (1200, 39)
        and area["delta"] == -1161
        and area["percent"] == pytest.approx(-96.75)
    )
    assert fit["constraints"]["violated"] == [] and "component_identity" in fit["constraints"]["satisfied"]
    assert (
        fit["lifecycle"] == "validated"
        and len(fit["candidate_hash"]) == 64
        and fit["changes"]["by_kind"] == {"set_outline_rect": 1}
    )
    assert "not a KiCad DRC result" in rep["verification_statement"]
    assert rep["analysis"]["area"]["available"] and rep["analysis"]["margins"]["profile"]["key"] == "via-conservative"
    assert set(rep["pareto"]) == {"outline_fit", "track_min_width"}


def test_report_markdown_and_isolation(client, make_client, design):
    run = start(
        client, design["id"], objectives=["area"], constraints={"requirements": [{"kind": "enclosure_fit"}]}
    ).json()
    resp = client.get(f"/api/v1/optimization-runs/{run['id']}/report?format=markdown")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/markdown")
    text = resp.text
    assert (
        text.startswith("# VIA Optimize report")
        and "Board area | 1200 mm²" in text
        and "| Board area | 1200 mm² | 39 mm²" in text
    )
    assert (
        "1 unverified" in text and "requirement:enclosure_fit" in text and "What this report does not establish" in text
    )
    assert "enclosure_fit" in text.split("do not establish")[-1] or "Constraints declared but not verifiable" in text
    stranger = make_client()
    register(stranger, "reportstranger@example.com")
    assert stranger.get(f"/api/v1/optimization-runs/{run['id']}/report").status_code == 404
    assert client.get(f"/api/v1/optimization-runs/{run['id']}/report?format=pdf").status_code == 422


def test_a_failed_run_leaves_the_design_untouched(client, design, monkeypatch):
    from via_api.services import optimizer

    def boom(*a, **k):
        raise RuntimeError("generator crashed")

    before = client.get(f"/api/v1/designs/{design['id']}").json()
    monkeypatch.setattr(optimizer, "optimize", boom)
    start(client, design["id"], objectives=["area"])
    runs = client.get(f"/api/v1/designs/{design['id']}/optimization-runs").json()
    assert runs and all(r["status"] != "succeeded" for r in runs)
    after = client.get(f"/api/v1/designs/{design['id']}").json()
    assert (after["current_revision"]["id"], after["revision_count"]) == (
        before["current_revision"]["id"],
        before["revision_count"],
    )
