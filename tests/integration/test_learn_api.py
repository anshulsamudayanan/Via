# ruff: noqa: F811  (test data; fixtures imported from test_intelligence_api are redefined as arguments)
"""VIA Learn through the API: feedback, contributions, review, withdrawal, retrieval and evaluation.

Recommendations come from the real review flow (a ScriptedProvider answering from the context VIA sent), so
the tests cover real context building, grounding checks and the audit trail.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select, update

from tests.integration.conftest import register
from tests.integration.test_intelligence_api import REF, analysed, ctx_of, grounded_review, use_provider  # noqa: F401
from via_api import ratelimit
from via_api.models import (
    ActivityLog,
    AIOutputKnowledge,
    LearnEntry,
    LearnEntryVersion,
    User,
)
from via_api.models.base import Base
from via_api.services.learn_scrub import GENERIC_NETS

ENTRY = {
    "category": "routing_practice",
    "title": "Match differential pair lengths",
    "description": "Keep differential pair skew under a tenth of the rise time by matching trace lengths.",
    "source": "own bench measurements",
    "confirm_rights": True,
}


def flag_reviewer(db, email: str) -> None:
    db.execute(update(User).where(User.email == email).values(learn_reviewer=True))
    db.flush()
    db.expire_all()


@pytest.fixture
def reviewer(make_client, db):
    c = make_client()
    register(c, "reviewer@example.com", "Reviewer")
    flag_reviewer(db, "reviewer@example.com")
    return c


@pytest.fixture
def author(make_client):
    c = make_client()
    register(c, "author@example.com", "Author")
    return c


@pytest.fixture
def other(make_client):
    c = make_client()
    register(c, "other@example.com", "Other")
    return c


def make_entry(client, **over) -> dict:
    resp = client.post("/api/v1/learn/contributions", json={**ENTRY, **over})
    assert resp.status_code == 201, resp.text
    return resp.json()


def publish(author, reviewer, verification="unverified", basis=None, **over) -> dict:
    e = make_entry(author, **over)
    assert author.post(f"/api/v1/learn/contributions/{e['id']}/submit").status_code == 200
    resp = reviewer.post(
        f"/api/v1/learn/contributions/{e['id']}/review",
        json={"decision": "approve", "verification_status": verification, "verification_basis": basis},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def search(client, q=None, **params) -> list[dict]:
    resp = client.get("/api/v1/learn/entries", params={**({"q": q} if q else {}), **params})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def board_review(use_provider, client, design_id, *, naming_board=False):
    """Run a real AI review and return its first recommendation. With ``naming_board`` the recommendation's
    text names a real part and a real net of the board."""
    seen: dict[str, str] = {}

    def fn(request, schema):
        ctx = ctx_of(request)
        ids = [f["id"] for f in ctx["findings"]]
        ref = ctx["components"][0]["reference"]
        net = next(n for n in ctx["net_names"] if n.upper() not in GENERIC_NETS)
        seen.update(ref=ref, net=net, project=ctx["design_name"])
        text = (
            f"Close the outline gap near {ref} on net {net} of design {ctx['design_name']}"
            if naming_board
            else "Close the outline gap"
        )
        return schema.model_validate(
            {
                "summary": "reviewed",
                "sections": [{"area": "design_rules", "verified_findings": ids[:1], "hypotheses": []}],
                "recommendations": [
                    {
                        "problem": text,
                        "proposed_change": f"Join the Edge.Cuts lines at {ref}"
                        if naming_board
                        else "Join the Edge.Cuts lines",
                        "rationale": "Fabricators need a closed outline",
                        "evidence_finding_ids": ids[:1],
                        "confidence": "high",
                        "uncertainty": "none",
                        "expected_benefits": ["Board can be fabricated"],
                        "trade_offs": [],
                        "required_validation": ["Re-run analysis"],
                        "references": [{"kind": "component", "id": ref}, {"kind": "net", "id": net}]
                        if naming_board
                        else [],
                    }
                ],
            }
        )

    use_provider(fn)
    resp = client.post(f"/api/v1/designs/{design_id}/ai/review", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()["recommendations"][0], seen


# --- feedback ---------------------------------------------------------------------------------------------------


def test_feedback_is_stored_with_versions_and_listed(client, analysed, use_provider):
    _, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"])
    url = f"/api/v1/recommendations/{rec['id']}/feedback"

    helpful = client.post(url, json={"feedback_type": "helpful"})
    assert helpful.status_code == 201, helpful.text
    row = helpful.json()
    assert row["category"] == "board_outline" and row["model"] == "scripted" and row["prompt_version"]
    assert row["mine"] is True and row["recommendation_id"] == rec["id"]

    assert client.post(url, json={"feedback_type": "correction"}).json()["error"]["code"] == "explanation_required"
    ok = client.post(
        url, json={"feedback_type": "incorrect_assumption", "explanation": "The outline is intentionally open here."}
    )
    assert ok.status_code == 201
    assert client.post(url, json={"feedback_type": "accepted"}).json()["error"]["code"] == "use_decision"

    history = client.get("/api/v1/learn/feedback", params={"recommendation_id": rec["id"]}).json()
    assert history["total"] == 2
    assert [r["feedback_type"] for r in history["items"]] == ["incorrect_assumption", "helpful"]


def test_accepting_or_rejecting_lands_in_the_feedback_history_but_is_not_proof(client, analysed, use_provider):
    _, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"])
    assert (
        client.patch(
            f"/api/v1/recommendations/{rec['id']}", json={"status": "rejected", "reason": "Not our fab rule"}
        ).status_code
        == 200
    )
    items = client.get("/api/v1/learn/feedback", params={"mine": True}).json()["items"]
    assert [(i["feedback_type"], i["explanation"]) for i in items] == [("rejected", "Not our fab rule")]
    evaluation = client.get("/api/v1/learn/evaluation").json()
    assert evaluation["summary"]["rejected"] == 1 and evaluation["summary"]["acceptance_rate"] == 0.0
    assert any("not measures of engineering accuracy" in n for n in evaluation["notes"])


def test_feedback_follows_project_roles_and_privacy(client, make_client, analysed, use_provider):
    project, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"])
    viewer, stranger = make_client(), make_client()
    register(viewer, "viewer@example.com", "Viewer")
    register(stranger, "stranger@example.com", "Stranger")
    client.post(f"/api/v1/projects/{project['id']}/members", json={"email": "viewer@example.com", "role": "viewer"})
    url = f"/api/v1/recommendations/{rec['id']}/feedback"
    assert viewer.post(url, json={"feedback_type": "helpful"}).status_code == 403  # editors give feedback
    assert stranger.post(url, json={"feedback_type": "helpful"}).status_code == 404
    client.post(url, json={"feedback_type": "helpful"})
    assert viewer.get("/api/v1/learn/feedback", params={"project_id": project["id"]}).json()["total"] == 1
    assert stranger.get("/api/v1/learn/feedback", params={"project_id": project["id"]}).status_code == 404
    assert stranger.get("/api/v1/learn/feedback").json()["total"] == 0  # nothing from projects they can't see


# --- contributions: free text -----------------------------------------------------------------------------------


def test_a_draft_is_private_and_only_approved_entries_are_searchable(author, reviewer, other):
    draft = make_entry(author)
    assert (
        draft["status"] == "draft" and draft["origin"] == "free_text" and draft["verification_status"] == "unverified"
    )
    assert other.get(f"/api/v1/learn/entries/{draft['id']}").status_code == 404
    assert reviewer.get(f"/api/v1/learn/entries/{draft['id']}").status_code == 404  # even reviewers don't see drafts
    assert search(other, "differential") == []

    assert author.post(f"/api/v1/learn/contributions/{draft['id']}/submit").status_code == 200
    assert search(other, "differential") == []  # waiting for review is still not shared
    queue = reviewer.get("/api/v1/learn/review").json()
    assert [e["id"] for e in queue["items"]] == [draft["id"]]

    approved = reviewer.post(f"/api/v1/learn/contributions/{draft['id']}/review", json={"decision": "approve"}).json()
    assert approved["status"] == "approved" and approved["verification_status"] == "unverified"
    hits = search(other, "differential pair skew")
    assert [h["id"] for h in hits] == [draft["id"]]
    assert hits[0]["mine"] is False and hits[0]["permissions"] is None and hits[0]["review_note"] is None
    assert "contributor" not in json.dumps(hits[0]).lower()  # no identity of the contributor is exposed


def test_rights_must_be_confirmed_before_a_draft_exists(author):
    resp = author.post("/api/v1/learn/contributions", json={**ENTRY, "confirm_rights": False})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "rights_required"
    assert author.get("/api/v1/learn/contributions").json()["total"] == 0


def test_review_rules(author, reviewer, db):
    e = make_entry(author)
    assert (
        reviewer.post(f"/api/v1/learn/contributions/{e['id']}/review", json={"decision": "approve"}).status_code == 404
    )
    author.post(f"/api/v1/learn/contributions/{e['id']}/submit")
    assert (
        reviewer.post(f"/api/v1/learn/contributions/{e['id']}/review", json={"decision": "reject"}).json()["error"][
            "code"
        ]
        == "reason_required"
    )
    needs_basis = reviewer.post(
        f"/api/v1/learn/contributions/{e['id']}/review", json={"decision": "approve", "verification_status": "verified"}
    )
    assert needs_basis.json()["error"]["code"] == "basis_required"
    rejected = reviewer.post(
        f"/api/v1/learn/contributions/{e['id']}/review", json={"decision": "reject", "note": "Too vague"}
    ).json()
    assert rejected["status"] == "rejected"
    assert search(reviewer, "differential") == []
    assert (
        author.get("/api/v1/learn/contributions", params={"status": "rejected"}).json()["items"][0]["review_note"]
        == "Too vague"
    )


def test_nobody_approves_their_own_contribution(make_client, db):
    a = make_client()
    register(a, "selfie@example.com", "Self")
    flag_reviewer(db, "selfie@example.com")
    e = make_entry(a)
    a.post(f"/api/v1/learn/contributions/{e['id']}/submit")
    r = a.post(f"/api/v1/learn/contributions/{e['id']}/review", json={"decision": "approve"})
    assert r.status_code == 403 and "your own" in r.json()["error"]["message"]


def test_verified_ranks_above_unverified_and_status_changes_are_versioned(author, reviewer):
    plain = publish(
        author,
        reviewer,
        title="Via stitching around RF traces",
        description="Stitching vias around RF traces tighten the return path.",
    )
    strong = publish(
        author,
        reviewer,
        verification="verified",
        basis="IPC-2221 section 6",
        title="Via stitching near RF lines",
        description="Stitching vias near RF lines tighten the return path.",
    )
    hits = search(author, "stitching vias RF return path")
    assert [h["id"] for h in hits] == [strong["id"], plain["id"]]
    assert hits[0]["score"] > hits[1]["score"]

    changed = reviewer.put(
        f"/api/v1/learn/entries/{plain['id']}/verification",
        json={"verification_status": "reviewed", "verification_basis": "Read and plausible"},
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    versions = author.get(f"/api/v1/learn/entries/{plain['id']}/versions").json()
    assert [(v["version"], v["change"], v["verification_status"]) for v in versions] == [
        (1, "created", "unverified"),
        (1, "approved", "unverified"),
        (2, "verification_changed", "reviewed"),
    ]
    assert (
        reviewer.put(
            f"/api/v1/learn/entries/{plain['id']}/verification", json={"verification_status": "verified"}
        ).json()["error"]["code"]
        == "basis_required"
    )


def test_permissions_control_library_and_ai_visibility(author, reviewer, other):
    e = publish(author, reviewer)
    url = f"/api/v1/learn/contributions/{e['id']}/permissions"
    assert other.put(url, json={"ai_retrieval": False}).status_code == 404  # only the contributor
    assert author.put(url, json={"ai_retrieval": False}).json()["permissions"] == {
        "library_visible": True,
        "ai_retrieval": False,
    }
    assert [h["id"] for h in search(other, "differential")] == [e["id"]]  # still in the library
    author.put(url, json={"library_visible": False})
    assert search(other, "differential") == []
    assert other.get(f"/api/v1/learn/entries/{e['id']}").status_code == 404
    assert author.get(f"/api/v1/learn/entries/{e['id']}").status_code == 200  # the contributor still sees theirs


def test_withdrawal_erases_content_keeps_provenance_and_stops_retrieval(author, reviewer, other, db):
    e = publish(author, reviewer)
    assert other.post(f"/api/v1/learn/contributions/{e['id']}/withdraw").status_code == 404
    out = author.post(f"/api/v1/learn/contributions/{e['id']}/withdraw").json()
    assert out["status"] == "withdrawn" and out["title"] == "[withdrawn]" and out["description"] == ""
    assert search(other, "differential") == []
    row = db.get(LearnEntry, uuid.UUID(e["id"]))
    assert row.contributor_id is not None and row.provenance["policy_version"] and row.withdrawn_at is not None
    assert row.technical_metadata == {} and row.source == ""
    versions = db.scalars(select(LearnEntryVersion).where(LearnEntryVersion.entry_id == row.id)).all()
    assert versions and all(v.description == "" and v.title == "[withdrawn]" for v in versions)
    actions = db.scalars(select(ActivityLog.action).where(ActivityLog.target_id == row.id)).all()
    assert {"learn.draft_created", "learn.submitted", "learn.approved", "learn.withdrawn"} <= set(actions)


def test_a_reviewer_can_take_an_entry_down(author, reviewer, other):
    e = publish(author, reviewer)
    assert reviewer.post(f"/api/v1/learn/contributions/{e['id']}/withdraw").json()["status"] == "withdrawn"
    assert other.post(f"/api/v1/learn/contributions/{e['id']}/withdraw").status_code == 404


def test_only_drafts_can_be_deleted(author, reviewer):
    d = make_entry(author)
    assert author.delete(f"/api/v1/learn/contributions/{d['id']}").status_code == 204
    published = publish(author, reviewer)
    assert author.delete(f"/api/v1/learn/contributions/{published['id']}").json()["error"]["code"] == "not_draft"


# --- contributions derived from a project -----------------------------------------------------------------------


def test_project_derived_contribution_needs_owner_consent_and_is_scrubbed(
    client, make_client, db, analysed, use_provider
):
    project, design, _ = analysed
    rec, seen = board_review(use_provider, client, design["id"], naming_board=True)
    url = f"/api/v1/recommendations/{rec['id']}/contribute"
    editor = make_client()
    register(editor, "editor@example.com", "Editor")
    client.post(f"/api/v1/projects/{project['id']}/members", json={"email": "editor@example.com", "role": "editor"})

    assert client.post(url, json={}).json()["error"]["code"] == "consent_required"
    assert editor.put(f"/api/v1/projects/{project['id']}/learn-consent").status_code == 403  # owner only
    assert client.put(f"/api/v1/projects/{project['id']}/learn-consent").json()["granted"] is True
    assert editor.post(url, json={}).status_code == 403  # contributing from a project is the owner's call

    draft = client.post(url, json={}).json()
    assert draft["status"] == "draft" and draft["origin"] == "project_derived"
    blob = json.dumps(draft)
    for secret in (seen["ref"], seen["net"], seen["project"], project["id"], design["id"], rec["id"]):
        assert secret not in blob, secret
    assert draft["provenance"]["scrub"]["parts"] >= 1 and draft["provenance"]["scrub"]["nets"] >= 1
    assert draft["provenance"]["ai_suggestion"] is True and draft["provenance"]["model"] == "scripted"
    assert "<part>" in draft["description"] and "<net>" in draft["description"]
    assert draft["verification_status"] == "unverified" and draft["category"] == "pcb_design_pattern"

    # Nothing is contributed until the owner submits, and nothing is shared until a reviewer approves.
    assert client.post(f"/api/v1/learn/contributions/{draft['id']}/submit").status_code == 200


def test_revoking_consent_withdraws_what_the_project_contributed(client, reviewer, other, analysed, use_provider):
    project, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"], naming_board=True)
    client.put(f"/api/v1/projects/{project['id']}/learn-consent")
    draft = client.post(f"/api/v1/recommendations/{rec['id']}/contribute", json={}).json()
    pending = client.post(f"/api/v1/recommendations/{rec['id']}/contribute", json={}).json()
    client.post(f"/api/v1/learn/contributions/{draft['id']}/submit")
    reviewer.post(f"/api/v1/learn/contributions/{draft['id']}/review", json={"decision": "approve"})
    assert len(search(other, "outline")) == 1

    gone = client.delete(f"/api/v1/projects/{project['id']}/learn-consent")
    assert gone.json()["granted"] is False and gone.json()["withdrawn_entries"] == 2
    assert search(other, "outline") == []
    assert client.post(f"/api/v1/learn/contributions/{pending['id']}/submit").status_code == 409  # now withdrawn
    assert (
        client.post(f"/api/v1/recommendations/{rec['id']}/contribute", json={}).json()["error"]["code"]
        == "consent_required"
    )


def test_revoking_without_withdrawing_keeps_existing_entries(client, reviewer, other, analysed, use_provider):
    project, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"], naming_board=True)
    client.put(f"/api/v1/projects/{project['id']}/learn-consent")
    draft = client.post(f"/api/v1/recommendations/{rec['id']}/contribute", json={}).json()
    client.post(f"/api/v1/learn/contributions/{draft['id']}/submit")
    reviewer.post(f"/api/v1/learn/contributions/{draft['id']}/review", json={"decision": "approve"})
    out = client.delete(f"/api/v1/projects/{project['id']}/learn-consent", params={"withdraw_existing": False}).json()
    assert out["withdrawn_entries"] == 0 and len(search(other, "outline")) == 1


def test_learn_store_has_no_foreign_keys_into_project_data():
    """The structural separation DATABASE.md promises: Learn tables reference only users, consent and each other."""
    allowed = {"users", "data_consents", "learn_entries"}
    for name in ("learn_entries", "learn_entry_versions"):
        targets = {fk.column.table.name for fk in Base.metadata.tables[name].foreign_keys}
        assert targets <= allowed, (name, targets)


def test_provenance_and_ownership_are_recorded(client, reviewer, db, analysed, use_provider):
    project, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"], naming_board=True)
    client.put(f"/api/v1/projects/{project['id']}/learn-consent")
    draft = client.post(f"/api/v1/recommendations/{rec['id']}/contribute", json={}).json()
    row = db.get(LearnEntry, uuid.UUID(draft["id"]))
    me = db.scalar(select(User).where(User.email == "ai@example.com"))
    assert row.contributor_id == me.id and row.consent_id is not None
    assert row.provenance["policy_version"] and row.provenance["derived_from"] == "ai_recommendation"
    dump = json.dumps([row.title, row.description, row.technical_metadata, row.source, row.provenance])
    assert project["id"] not in dump and design["id"] not in dump
    audit = db.scalars(
        select(ActivityLog).where(ActivityLog.target_id == row.id, ActivityLog.action == "learn.draft_created")
    ).one()
    assert str(audit.project_id) == project["id"]  # the *project's* private audit log records it


# --- retrieval by the AI ----------------------------------------------------------------------------------------


def explain_citing_knowledge(request, schema):
    ctx = ctx_of(request)
    refs = [{"kind": "finding", "id": ctx["findings"][0]["id"]}]
    if ctx.get("knowledge"):
        refs.append({"kind": "knowledge", "id": ctx["knowledge"][0]["id"]})
    return schema.model_validate({"answer": "See the cited finding and note.", "references": refs})


def ask(client, design_id, question="How should the outline gap be closed?"):
    return client.post(f"/api/v1/designs/{design_id}/ai/explain", json={"question": question})


def test_approved_knowledge_reaches_the_ai_with_provenance_and_influence_is_tracked(
    client, reviewer, db, analysed, use_provider
):
    _, design, _ = analysed
    e = publish(
        client,
        reviewer,
        verification="verified",
        basis="IPC-2221",
        title="Close the board outline gap",
        description="An open board outline is rejected by fabricators; join the Edge.Cuts lines into one closed loop.",
        category="manufacturing_constraint",
    )
    provider = use_provider(explain_citing_knowledge)
    out = ask(client, design["id"])
    assert out.status_code == 200, out.text
    shown = ctx_of(provider.requests[-1])["knowledge"]
    assert [k["id"] for k in shown] == [e["id"]]
    assert (
        shown[0]["verification"] == "verified"
        and shown[0]["source"] == "own bench measurements"
        and shown[0]["version"] == 1
    )
    link = db.scalars(select(AIOutputKnowledge).where(AIOutputKnowledge.entry_id == uuid.UUID(e["id"]))).one()
    assert (
        link.cited is True
        and link.entry_version == 1
        and link.rank == 0
        and link.ai_output_id == uuid.UUID(out.json()["id"])
    )


def test_retrieved_but_uncited_knowledge_is_recorded_as_not_influential(client, reviewer, db, analysed, use_provider):
    _, design, _ = analysed
    e = publish(
        client,
        reviewer,
        title="Close the board outline gap",
        description="Join the Edge.Cuts lines of an open board outline into one closed loop.",
    )
    provider = use_provider(
        lambda request, schema: schema.model_validate(
            {"answer": "x", "references": [{"kind": "finding", "id": ctx_of(request)["findings"][0]["id"]}]}
        )
    )
    assert ask(client, design["id"]).status_code == 200
    link = db.scalars(select(AIOutputKnowledge).where(AIOutputKnowledge.entry_id == uuid.UUID(e["id"]))).one()
    assert link.cited is False and len(provider.requests) == 1


def test_recommendations_list_the_library_notes_shown_to_the_model_with_attribution(
    client, reviewer, analysed, use_provider
):
    _, design, _ = analysed
    e = publish(
        client,
        reviewer,
        title="Close the board outline gap",
        description="Join the Edge.Cuts lines of an open board outline into one closed loop.",
    )
    rec, _ = board_review(use_provider, client, design["id"])
    shown = [(k["entry_id"], k["cited"], k["verification_status"], k["source"]) for k in rec["knowledge"]]
    assert shown == [(e["id"], False, "unverified", "own bench measurements")]  # shown to the model, not cited
    listed = client.get(f"/api/v1/designs/{design['id']}/recommendations").json()
    assert listed[0]["knowledge"] == rec["knowledge"]


def test_citing_knowledge_that_was_not_retrieved_is_rejected(client, analysed, use_provider):
    _, design, _ = analysed
    use_provider(
        lambda request, schema: schema.model_validate(
            {"answer": "x", "references": [{"kind": "knowledge", "id": str(uuid.uuid4())}]}
        )
    )
    r = ask(client, design["id"])
    assert r.status_code == 502 and r.json()["error"]["code"] == "ai_output_rejected"
    assert any("knowledge:" in p for p in r.json()["error"]["details"]["problems"])


def test_only_approved_and_permitted_entries_are_retrieved(client, reviewer, analysed, use_provider):
    _, design, _ = analysed
    text = {
        "title": "Close the board outline gap",
        "description": "Join the Edge.Cuts lines of an open board outline into one closed loop.",
    }
    make_entry(client, **text)  # a draft
    pending = make_entry(client, **text)
    client.post(f"/api/v1/learn/contributions/{pending['id']}/submit")
    hidden = publish(client, reviewer, **text)
    client.put(f"/api/v1/learn/contributions/{hidden['id']}/permissions", json={"ai_retrieval": False})
    gone = publish(client, reviewer, **text)
    client.post(f"/api/v1/learn/contributions/{gone['id']}/withdraw")
    ok = publish(client, reviewer, **text)
    provider = use_provider(explain_citing_knowledge)
    assert ask(client, design["id"]).status_code == 200
    assert [k["id"] for k in ctx_of(provider.requests[-1])["knowledge"]] == [ok["id"]]


def test_knowledge_is_capped_and_unverified_is_labelled(client, reviewer, analysed, use_provider):
    _, design, _ = analysed
    for i in range(5):
        publish(
            client,
            reviewer,
            title=f"Close the board outline gap {i}",
            description=("Join the open board outline. " + "Detail. " * 300),
        )
    provider = use_provider(explain_citing_knowledge)
    assert ask(client, design["id"]).status_code == 200
    shown = ctx_of(provider.requests[-1])["knowledge"]
    assert (
        len(shown) == 3
        and all(len(k["text"]) <= 600 for k in shown)
        and {k["verification"] for k in shown} == {"unverified"}
    )
    assert "unverified" in provider.requests[-1].system  # the prompt tells the model how to treat it


def test_private_project_content_never_comes_back_as_knowledge(client, make_client, reviewer, analysed, use_provider):
    """Another user's private recommendation text is not searchable and never reaches anyone's AI context."""
    _, design, _ = analysed
    secret = "zzzquuxsecret"
    use_provider(
        lambda request, schema: schema.model_validate(
            {
                "summary": "s",
                "sections": [],
                "recommendations": [
                    {
                        "problem": f"{secret} outline",
                        "proposed_change": f"{secret} fix",
                        "rationale": secret,
                        "confidence": "low",
                        "uncertainty": "n",
                        "evidence_finding_ids": [ctx_of(request)["findings"][0]["id"]],
                    }
                ],
            }
        )
    )
    assert client.post(f"/api/v1/designs/{design['id']}/ai/review", json={}).status_code == 200

    spy = make_client()
    register(spy, "spy@example.com", "Spy")
    assert search(spy, secret) == [] and search(reviewer, secret) == []
    project = spy.post("/api/v1/projects", json={"name": "Theirs"}).json()
    own = spy.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("b.kicad_pcb", REF.encode(), "application/octet-stream")},
    ).json()
    spy.post(
        f"/api/v1/designs/{own['design']['id']}/analysis-runs",
        json={"checks": ["board_outline", "design_rules_source"]},
    )
    provider = use_provider(lambda request, schema: schema.model_validate({"answer": "x", "references": []}))
    assert (
        spy.post(
            f"/api/v1/designs/{own['design']['id']}/ai/explain", json={"question": f"What about {secret}?"}
        ).status_code
        == 200
    )
    assert ctx_of(provider.requests[-1]).get("knowledge", []) == []
    assert secret not in provider.requests[-1].messages[0].content.replace(f"What about {secret}?", "")


# --- evaluation -------------------------------------------------------------------------------------------------


def test_evaluation_measures_decisions_opinions_grounding_and_evidence_resolution(
    client, make_client, reviewer, analysed, use_provider
):
    project, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"])
    client.post(f"/api/v1/recommendations/{rec['id']}/feedback", json={"feedback_type": "helpful"})
    client.post(
        f"/api/v1/recommendations/{rec['id']}/feedback",
        json={"feedback_type": "correction", "explanation": "Close it at the corner instead."},
    )
    client.patch(f"/api/v1/recommendations/{rec['id']}", json={"status": "accepted"})
    # A review the grounding check discards (cites a part that isn't on the board).
    use_provider(
        lambda request, schema: schema.model_validate(
            {
                "summary": "s",
                "sections": [],
                "recommendations": [
                    {
                        "problem": "Move U99",
                        "proposed_change": "x",
                        "rationale": "y",
                        "confidence": "low",
                        "uncertainty": "n",
                        "references": [{"kind": "component", "id": "U99"}],
                    }
                ],
            }
        )
    )
    assert client.post(f"/api/v1/designs/{design['id']}/ai/review", json={}).status_code == 502

    first = client.get("/api/v1/learn/evaluation", params={"project_id": project["id"]}).json()
    s = first["summary"]
    assert (
        s["recommendations"],
        s["accepted"],
        s["acceptance_rate"],
        s["helpful"],
        s["helpful_rate"],
        s["corrections"],
    ) == (1, 1, 1.0, 1, 1.0, 1)
    assert first["grounding"] == {"reviews": 2, "rejected": 1, "rejection_rate": 0.5}
    assert s["evidence_not_checkable"] == 1 and s["evidence_resolution_rate"] is None  # no newer revision yet
    assert first["by_category"][0]["category"] == "board_outline"
    assert first["by_version"][0]["model"] == "scripted" and first["by_version"][0]["grounding_rejection_rate"] == 0.5
    assert "layers" in first["by_board_bucket"][0]["bucket"]
    assert {m["metric"] for m in first["not_measurable"]} == {
        "false positive and false negative rates",
        "accuracy by PCB type",
    }

    checks = ["board_outline", "design_rules_source"]
    # Fixed board uploaded as a newer revision and analysed: the evidence finding is gone ("resolved").
    client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"], "design_id": design["id"]},
        files={"file": ("v2.kicad_pcb", REF.encode(), "application/octet-stream")},
    )
    client.post(f"/api/v1/designs/{design['id']}/analysis-runs", json={"checks": checks})
    s = client.get("/api/v1/learn/evaluation", params={"project_id": project["id"]}).json()["summary"]
    assert (s["evidence_resolved"], s["evidence_persisting"], s["evidence_resolution_rate"]) == (1, 0, 1.0)

    # A newer revision that still has the problem: "persisting".
    broken = REF.replace(
        "(start 150 100)\n\t\t(end 150 130)", "(start 150 100)\n\t\t(end 150 128)"
    )  # differs from v1, so it is a new revision
    assert broken != REF
    client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"], "design_id": design["id"]},
        files={"file": ("v3.kicad_pcb", broken.encode(), "application/octet-stream")},
    )
    client.post(f"/api/v1/designs/{design['id']}/analysis-runs", json={"checks": checks})
    s = client.get("/api/v1/learn/evaluation", params={"project_id": project["id"]}).json()["summary"]
    assert (s["evidence_resolved"], s["evidence_persisting"]) == (0, 1)


def test_evaluation_access_and_global_view(client, make_client, reviewer, analysed, use_provider):
    project, design, _ = analysed
    rec, _ = board_review(use_provider, client, design["id"])
    client.patch(f"/api/v1/recommendations/{rec['id']}", json={"status": "accepted"})
    stranger = make_client()
    register(stranger, "nosy@example.com", "Nosy")
    assert stranger.get("/api/v1/learn/evaluation", params={"project_id": project["id"]}).status_code == 404
    assert (
        stranger.get("/api/v1/learn/evaluation").json()["summary"]["recommendations"] == 0
    )  # only projects they can see
    assert stranger.get("/api/v1/learn/evaluation/global").status_code == 403
    g = reviewer.get("/api/v1/learn/evaluation/global").json()
    assert g["scope"] == "global" and g["summary"]["recommendations"] == 1
    assert "Close the outline gap" not in json.dumps(g) and project["id"] not in json.dumps(g)  # counts and rates only


# --- meta, consent, limits, cli ---------------------------------------------------------------------------------


def test_meta_says_retrieval_is_keyword_based(author):
    meta = author.get("/api/v1/learn/meta").json()
    assert meta["retrieval"]["semantic"] is False and meta["is_reviewer"] is False
    assert "manufacturing_constraint" in meta["categories"] and len(meta["verification_levels"]) == 3


def test_learn_consent_is_off_by_default_and_owner_managed(client, analysed):
    project, _, _ = analysed
    assert client.get(f"/api/v1/projects/{project['id']}/learn-consent").json()["granted"] is False
    assert client.put(f"/api/v1/projects/{project['id']}/learn-consent").json()["granted"] is True
    assert client.get(f"/api/v1/projects/{project['id']}/learn-consent").json()["granted_at"]
    # Granting Learn consent doesn't grant AI or supplier consent (separate scopes).
    assert client.get(f"/api/v1/ai/consent/{project['id']}").json()["granted"] is False


def test_library_reads_are_rate_limited(make_client, test_redis):
    reader = make_client()
    me = register(reader, "reader@example.com", "Reader")
    key = f"via:rl:{ratelimit.LEARN_READS_PER_USER.name}:{me['user']['id']}"
    test_redis.set(key, ratelimit.LEARN_READS_PER_USER.max_requests, ex=3600)
    assert reader.get("/api/v1/learn/entries").status_code == 429


def test_cli_grants_and_removes_the_reviewer_flag(db, make_client, monkeypatch, capsys):
    from via_api import cli
    from via_api import db as db_module

    class Ctx:
        def __enter__(self):
            return db

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db_module, "get_sessionmaker", lambda: lambda: Ctx())
    c = make_client()
    register(c, "future-reviewer@example.com", "Future")
    assert cli._learn_reviewer("Future-Reviewer@example.com", revoke=False) == 0
    db.expire_all()
    assert c.get("/api/v1/learn/meta").json()["is_reviewer"] is True
    assert cli._learn_reviewer("future-reviewer@example.com", revoke=True) == 0
    db.expire_all()
    assert c.get("/api/v1/learn/meta").json()["is_reviewer"] is False
    assert cli._learn_reviewer("nobody@example.com", revoke=False) == 1
