# ruff: noqa: E501  (test data)
"""AI explanations, design reviews, recommendations and component records through the API.

The provider is a ScriptedProvider whose answers are built from the context VIA actually sent, so
these tests exercise the real context building, consent gate, verification and audit trail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.integration.conftest import register
from via_ai.providers.scripted import ScriptedProvider
from via_api.ai import get_ai_provider
from via_api.models import AIOutput

FIXTURES = Path(__file__).resolve().parents[1] / "engineering" / "fixtures"
REF = (FIXTURES / "via_reference_v8.kicad_pcb").read_text()


def ctx_of(request) -> dict:
    content = request.messages[0].content
    return json.loads(content[content.index("CONTEXT:\n") + len("CONTEXT:\n") :])


def grounded_explanation(request, schema):
    ctx = ctx_of(request)
    f = ctx["findings"][0]
    return schema.model_validate(
        {
            "answer": f"{f['title']}: see the cited finding.",
            "references": [{"kind": "finding", "id": f["id"]}]
            + [{"kind": "component", "id": c} for c in f["components"][:1]],
            "numbers_used": [],
            "uncertainties": ["The schematic isn't in the context."],
        }
    )


def invented_explanation(request, schema):
    return schema.model_validate(
        {"answer": "Move U99 next to the regulator.", "references": [{"kind": "component", "id": "U99"}]}
    )


def grounded_review(request, schema):
    ctx = ctx_of(request)
    ids = [f["id"] for f in ctx["findings"]]
    return schema.model_validate(
        {
            "summary": f"{len(ids)} findings reviewed.",
            "sections": [{"area": "design_rules", "verified_findings": ids[:3], "hypotheses": []}],
            "recommendations": [
                {
                    "problem": "Board outline is open",
                    "proposed_change": "Close the Edge.Cuts outline",
                    "rationale": "Fabricators need a closed outline",
                    "evidence_finding_ids": ids[:1],
                    "confidence": "high",
                    "uncertainty": "None significant",
                    "expected_benefits": ["Board can be fabricated"],
                    "trade_offs": [],
                    "required_validation": ["Re-run analysis"],
                }
            ],
        }
    )


@pytest.fixture
def use_provider(app):
    def install(*outputs, external=False):
        provider = ScriptedProvider(list(outputs), external=external)
        app.dependency_overrides[get_ai_provider] = lambda: provider
        return provider

    yield install
    app.dependency_overrides.pop(get_ai_provider, None)


@pytest.fixture
def analysed(client):
    """A parsed board with an open outline, analysed with the outline check only."""
    register(client, "ai@example.com", "Ada")
    project = client.post("/api/v1/projects", json={"name": "AI"}).json()
    broken = REF.replace(
        """	(gr_line
		(start 150 100)
		(end 150 130)""",
        """	(gr_line
		(start 150 100)
		(end 150 129)""",
    )  # one outline line now stops 1 mm short: open outline
    imported = client.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                           files={"file": ("ref.kicad_pcb", broken.encode(), "application/octet-stream")}).json()  # fmt: skip
    design = imported["design"]
    run = client.post(
        f"/api/v1/designs/{design['id']}/analysis-runs", json={"checks": ["board_outline", "design_rules_source"]}
    ).json()
    return project, design, run


def test_ai_disabled_by_default(client, analysed):
    _, design, _ = analysed
    resp = client.post(f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "What's wrong?"})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "ai_disabled"


def test_explanation_is_grounded_labelled_and_audited(client, analysed, use_provider, db):
    _, design, run = analysed
    provider = use_provider(grounded_explanation)
    resp = client.post(
        f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "What's the most serious problem?"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "ai_suggestion" and body["verification"] == "unverified"
    assert body["grounding"]["ok"] is True and body["analysis_run_id"] == run["id"]
    sent = ctx_of(provider.requests[0])
    assert [f["rule"] for f in sent["findings"]] == ["outline_open", "project_rules_missing"]
    assert any("Unjoined outline endpoints: 2" in e for e in sent["findings"][0]["evidence"])
    assert "storage_key" not in json.dumps(sent) and "@example.com" not in json.dumps(sent)  # no internals or emails
    row = db.scalars(select(AIOutput)).one()
    assert row.accepted and row.prompt_version and len(row.context_sha256) == 64


def test_invented_references_are_rejected_and_kept_for_audit(client, analysed, use_provider, db):
    _, design, _ = analysed
    use_provider(invented_explanation)
    resp = client.post(f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "Improve placement?"})
    assert resp.status_code == 502 and resp.json()["error"]["code"] == "ai_output_rejected"
    assert any("U99" in p for p in resp.json()["error"]["details"]["problems"])
    row = db.scalars(select(AIOutput)).one()
    assert row.accepted is False


def test_focus_on_finding_component_and_net(client, analysed, use_provider):
    _, design, run = analysed
    finding = client.get(f"/api/v1/analysis-runs/{run['id']}/findings").json()["items"][0]
    provider = use_provider(grounded_explanation, grounded_explanation, grounded_explanation)
    assert client.post(f"/api/v1/findings/{finding['id']}/explain", json={}).status_code == 200
    assert ctx_of(provider.requests[0])["focus"]["kind"] == "finding"
    resp = client.post(
        f"/api/v1/designs/{design['id']}/ai/explain",
        json={"question": "Why here?", "focus": {"kind": "component", "id": "R1"}},
    )
    assert resp.status_code == 200 and ctx_of(provider.requests[1])["focus"]["details"]["footprint"]
    resp = client.post(
        f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "Net?", "focus": {"kind": "net", "id": "GND"}}
    )
    assert resp.status_code == 200 and ctx_of(provider.requests[2])["focus"]["details"]["pads"] >= 1
    missing = client.post(
        f"/api/v1/designs/{design['id']}/ai/explain",
        json={"question": "?", "focus": {"kind": "component", "id": "U42"}},
    )
    assert missing.status_code == 404


def test_external_providers_need_consent(client, analysed, use_provider):
    project, design, _ = analysed
    use_provider(grounded_explanation, grounded_explanation, external=True)
    resp = client.post(f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "?"})
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "consent_required"
    client.put(f"/api/v1/ai/consent/{project['id']}")
    assert client.post(f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "?"}).status_code == 200


def test_design_review_stores_recommendations(client, analysed, use_provider):
    _, design, _ = analysed
    use_provider(grounded_review)
    resp = client.post(f"/api/v1/designs/{design['id']}/ai/review", json={})
    assert resp.status_code == 200, resp.text
    (rec,) = resp.json()["recommendations"]
    assert rec["source"] == "ai_suggestion" and rec["verification"] == "unverified" and rec["status"] == "open"
    assert rec["evidence_finding_ids"] and rec["required_validation"] == ["Re-run analysis"]
    listed = client.get(f"/api/v1/designs/{design['id']}/recommendations").json()
    assert [r["id"] for r in listed] == [rec["id"]]
    updated = client.patch(
        f"/api/v1/recommendations/{rec['id']}", json={"status": "accepted", "reason": "Will fix"}
    ).json()
    assert updated["status"] == "accepted"
    assert client.get(f"/api/v1/designs/{design['id']}/recommendations", params={"status": "open"}).json() == []


def test_viewers_can_explain_but_not_review(client, make_client, analysed, use_provider):
    project, design, _ = analysed
    viewer = make_client()
    register(viewer, "aiviewer@example.com")
    client.post(f"/api/v1/projects/{project['id']}/members", json={"email": "aiviewer@example.com", "role": "viewer"})
    use_provider(grounded_explanation)
    assert viewer.post(f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "?"}).status_code == 200
    assert viewer.post(f"/api/v1/designs/{design['id']}/ai/review", json={}).status_code == 403


def test_component_records_and_matches(client, analysed, use_provider):
    project, design, _ = analysed
    url = f"/api/v1/projects/{project['id']}/component-records"
    rec = client.post(url, json={
        "manufacturer": "Yageo", "part_number": "RC0603FR-0710KL", "package": "0603", "source": "entered by user",
        "specs": [{"name": "Resistance", "value": "10", "unit": "kΩ", "source": "Yageo datasheet RC_L, p.3", "verified": True}],
        "datasheets": [{"url": "https://example.invalid/rc.pdf", "title": "RC series"}],
    })  # fmt: skip
    assert rec.status_code == 201, rec.text
    assert client.post(url, json={**rec.json(), "id": None}).status_code in (409, 422)
    # The reference board's footprints carry no part number properties: nothing matches, nothing is invented.
    matches = client.get(f"/api/v1/designs/{design['id']}/component-matches").json()
    assert matches and all(m["part_number"] is None and m["record_id"] is None for m in matches)
    assert client.get(url, params={"q": "rc0603"}).json()[0]["part_number"] == "RC0603FR-0710KL"
    rid = rec.json()["id"]
    assert (
        client.patch(f"/api/v1/component-records/{rid}", json={"verification": "verified"}).json()["verification"]
        == "verified"
    )
    assert client.delete(f"/api/v1/component-records/{rid}").status_code == 204


def test_part_numbers_are_read_from_footprint_properties(client, use_provider):
    register(client, "mpn@example.com")
    project = client.post("/api/v1/projects", json={"name": "MPN"}).json()
    board = REF.replace(
        '(property "Reference" "R1"',
        '(property "MPN" "RC0603FR-0710KL" (at 0 0 0) (layer "F.Fab"))\n\t\t(property "Reference" "R1"',
        1,
    )
    design = client.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                         files={"file": ("m.kicad_pcb", board.encode(), "application/octet-stream")}).json()["design"]  # fmt: skip
    rec = client.post(f"/api/v1/projects/{project['id']}/component-records", json={
        "manufacturer": "Yageo", "part_number": "RC0603FR-0710KL", "source": "entered by user",
        "specs": [{"name": "Power", "value": "0.1", "unit": "W", "source": "datasheet p.3"}]}).json()  # fmt: skip
    r1 = next(
        m for m in client.get(f"/api/v1/designs/{design['id']}/component-matches").json() if m["reference"] == "R1"
    )
    assert (r1["part_number"], r1["record_id"]) == ("RC0603FR-0710KL", rec["id"])
    provider = use_provider(lambda req, schema: schema.model_validate({"answer": "ok"}))
    client.post(f"/api/v1/designs/{design['id']}/ai/explain", json={"question": "R1 rating?"})
    (record,) = ctx_of(provider.requests[0])["component_records"]
    assert record["references"] == ["R1"] and record["specs"] == ["Power: 0.1 W (datasheet p.3, unverified)"]
