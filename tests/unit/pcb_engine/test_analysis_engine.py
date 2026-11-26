"""Analysis engine behaviour: isolation, skips, attribution, fingerprints, ordering."""

from __future__ import annotations

from pathlib import Path

import pytest

from via_pcb import parse_pcb
from via_pcb.analysis import (
    AnalysisEngine,
    Category,
    Check,
    CheckRegistry,
    CheckStatus,
    Finding,
    ObjectKind,
    ObjectRef,
    Severity,
    Source,
    default_registry,
)

REF = Path(__file__).resolve().parents[2] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb"


@pytest.fixture(scope="module")
def design():
    return parse_pcb(REF)


def finding(check_id: str, rule: str, severity: Severity, **kw) -> Finding:
    return Finding(
        check_id=check_id, rule=rule, category=Category.GEOMETRY, severity=severity,
        title=kw.pop("title", rule), description="d", explanation="e", **kw,
    )  # fmt: skip


class Yields(Check):
    category = Category.GEOMETRY
    title = description = "t"
    version = "1.0.0"

    def __init__(self, check_id, findings):
        self.id = check_id
        self._findings = findings

    def run(self, ctx):
        return self._findings


class Boom(Yields):
    def run(self, ctx):
        raise RuntimeError("internal detail that must not leak")


class Skips(Yields):
    def skip_reason(self, ctx):
        return "Not applicable here."


def engine(*checks: Check) -> AnalysisEngine:
    reg = CheckRegistry()
    for c in checks:
        reg.register(c)
    return AnalysisEngine(reg)


def test_failing_check_is_isolated_and_reported_without_details(design):
    ok = Yields("ok", [finding("ok", "r", Severity.LOW)])
    result = engine(Boom("boom", []), ok).run(design)
    runs = {r.check_id: r for r in result.checks}
    assert runs["boom"].status == CheckStatus.ERROR and runs["boom"].message == "RuntimeError"
    assert runs["ok"].status == CheckStatus.OK and runs["ok"].finding_count == 1
    assert len(result.findings) == 1


def test_skipped_check_records_its_reason(design):
    result = engine(Skips("skip", [finding("skip", "r", Severity.LOW)])).run(design)
    assert result.checks[0].status == CheckStatus.SKIPPED
    assert result.checks[0].message == "Not applicable here."
    assert result.findings == []


def test_findings_attributed_to_another_check_or_source_are_rejected(design):
    liar = Yields("liar", [finding("someone_else", "r", Severity.LOW)])
    fake_drc = Yields("fake", [finding("fake", "r", Severity.LOW, source=Source.KICAD_DRC)])
    result = engine(liar, fake_drc).run(design)
    assert [r.status for r in result.checks] == [CheckStatus.ERROR, CheckStatus.ERROR]
    assert result.findings == []


def test_findings_are_sorted_by_severity(design):
    c = Yields(
        "c",
        [finding("c", "a", Severity.INFO), finding("c", "b", Severity.CRITICAL), finding("c", "x", Severity.MEDIUM)],
    )
    assert [f.severity for f in engine(c).run(design).findings] == [Severity.CRITICAL, Severity.MEDIUM, Severity.INFO]


def test_fingerprints_depend_on_what_the_issue_is_about_not_on_measured_values():
    a = finding(
        "c",
        "gap",
        Severity.LOW,
        objects=[ObjectRef(kind=ObjectKind.TRACK, id="t2"), ObjectRef(kind=ObjectKind.TRACK, id="t1")],
    )
    b = finding(
        "c",
        "gap",
        Severity.HIGH,
        title="different text",
        objects=[ObjectRef(kind=ObjectKind.TRACK, id="t1"), ObjectRef(kind=ObjectKind.TRACK, id="t2")],
    )
    other = finding("c", "gap", Severity.LOW, objects=[ObjectRef(kind=ObjectKind.TRACK, id="t3")])
    assert a.with_fingerprint().fingerprint == b.with_fingerprint().fingerprint
    assert a.fingerprint != other.with_fingerprint().fingerprint
    assert len(a.fingerprint) == 32


def test_engine_fills_missing_fingerprints(design):
    result = engine(Yields("c", [finding("c", "r", Severity.LOW)])).run(design)
    assert result.findings[0].fingerprint


def test_result_records_versions(design):
    result = engine().run(design)
    assert result.design_schema_version == design.schema_version
    assert result.analysis_version and result.engine_version


def test_only_runs_selected_checks(design):
    result = AnalysisEngine(default_registry()).run(design, only={"board_outline"})
    assert [r.check_id for r in result.checks] == ["board_outline"]


def test_default_checks_have_unique_ids_and_metadata():
    checks = default_registry().all()
    assert len({c.id for c in checks}) == len(checks) >= 4
    for c in checks:
        assert c.version and c.title and c.description and isinstance(c.category, Category)
        assert c.source == Source.VIA_DETERMINISTIC


def test_confidence_is_bounded():
    with pytest.raises(ValueError):
        finding("c", "r", Severity.LOW, confidence=1.5)
