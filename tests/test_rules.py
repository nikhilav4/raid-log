import datetime as dt

import pytest

from raid_log.findings import Level
from raid_log.rules import validate

from .factories import TODAY, load_items, make_item

CLOSED_LOG = [{"date": dt.date(2026, 10, 20), "note": "Closed at steering committee"}]


def findings_for(*items, **header):
    return validate(load_items(*items, **header), TODAY)


def rules(findings, level=None):
    return sorted(f.rule for f in findings if level is None or f.level is level)


def test_clean_register_has_no_findings():
    findings = findings_for(
        make_item("R-001", probability=4, impact=5, mitigation="Weekly vendor checkpoint"),
        make_item("A-001"),
        make_item("I-001", links=["R-001"]),
        make_item("D-001"),
        make_item("I-002", status="resolved", resolution="Patched in 4.2.1", log=CLOSED_LOG),
    )
    assert findings == []


def test_duplicate_id_points_at_the_first_use():
    findings = findings_for(make_item("R-001"), make_item("R-001"))

    (dup,) = [f for f in findings if f.rule == "duplicate-id"]
    assert dup.level is Level.ERROR
    assert "first used on line" in dup.message


def test_id_prefix_must_match_type():
    findings = findings_for(make_item("R-001", type="issue", severity="low"))

    assert rules(findings) == ["id-prefix"]


@pytest.mark.parametrize("owner", [None, "", "   "])
def test_owner_is_required(owner):
    assert rules(findings_for(make_item("I-001", owner=owner))) == ["missing-owner"]


def test_links_must_resolve():
    findings = findings_for(make_item("R-001", links=["D-009", "R-001"]))

    assert rules(findings, Level.ERROR) == ["broken-link"]
    assert rules(findings, Level.WARNING) == ["self-link"]
    assert "D-009" in findings[0].message


def test_links_to_items_with_schema_errors_still_resolve():
    broken = make_item("D-001", status="blocked")
    findings = findings_for(make_item("R-001", links=["D-001"]), broken)

    assert rules(findings) == ["schema"]


def test_active_items_need_a_review_date():
    findings = findings_for(make_item("I-001", status="mitigating", review_by=None))

    assert rules(findings) == ["missing-review-date"]


def test_overdue_review_is_a_warning_not_an_error():
    findings = findings_for(make_item("I-001", review_by=dt.date(2026, 10, 21)))

    assert [(f.level, f.rule, f.message) for f in findings] == [
        (Level.WARNING, "review-overdue", "review was due 2026-10-21 (7 days ago)")
    ]


def test_closed_items_need_a_resolution_but_no_review_date():
    findings = findings_for(make_item("I-001", status="closed", review_by=None, log=CLOSED_LOG))

    assert rules(findings) == ["missing-resolution"]


def test_closure_without_a_log_entry_is_flagged():
    findings = findings_for(make_item("I-001", status="resolved", resolution="Fixed"))

    assert rules(findings, Level.WARNING) == ["undated-closure"]


def test_risks_need_probability_and_impact():
    assert rules(findings_for(make_item("R-001", impact=None))) == ["missing-rating"]


@pytest.mark.parametrize(
    ("probability", "impact", "expected"),
    [(3, 4, ["unmitigated-risk"]), (4, 3, ["unmitigated-risk"]), (2, 5, []), (5, 2, [])],
)
def test_exposure_of_12_or_more_needs_a_mitigation(probability, impact, expected):
    item = make_item("R-001", probability=probability, impact=impact)
    assert rules(findings_for(item)) == expected


def test_closed_high_exposure_risk_is_not_asked_for_a_mitigation():
    item = make_item(
        "R-001",
        probability=5,
        impact=5,
        status="closed",
        resolution="Vendor delivered",
        log=CLOSED_LOG,
    )
    assert findings_for(item) == []


@pytest.mark.parametrize("missing", ["counterparty", "need_by"])
def test_dependencies_need_counterparty_and_need_by(missing):
    findings = findings_for(make_item("D-001", **{missing: None}))

    assert rules(findings) == ["dependency-details"]
    assert missing in findings[0].message


def test_passed_need_by_on_open_dependency_is_a_warning():
    findings = findings_for(make_item("D-001", need_by=dt.date(2026, 10, 27)))

    assert [(f.level, f.rule) for f in findings] == [(Level.WARNING, "need-by-passed")]


def test_assumption_validation_dates():
    no_date = findings_for(make_item("A-001", validate_by=None))
    passed = findings_for(make_item("A-001", validate_by=dt.date(2026, 10, 1)))

    assert rules(no_date) == ["missing-validate-by"]
    assert rules(passed) == ["validate-by-passed"]


def test_issue_without_severity_is_a_warning():
    assert rules(findings_for(make_item("I-001", severity=None)), Level.WARNING) == [
        "missing-severity"
    ]


def test_unknown_fields_suggest_the_likely_key():
    findings = findings_for(make_item("R-001", reviewby=dt.date(2026, 11, 1)))

    (unknown,) = findings
    assert unknown.level is Level.WARNING
    assert unknown.message == "unknown field `reviewby`; did you mean `review_by`?"


def test_fields_for_another_type_are_flagged():
    findings = findings_for(make_item("I-001", probability=3))

    assert rules(findings) == ["wrong-type-field"]
    assert "probability only applies to risks" in findings[0].message


def test_review_date_before_raised():
    item = make_item("R-001", raised=dt.date(2026, 11, 2), review_by=dt.date(2026, 11, 1))
    assert rules(findings_for(item, updated=dt.date(2026, 11, 2))) == ["date-order"]


def test_stale_updated_date():
    item = make_item("R-001", raised=dt.date(2026, 10, 25))
    findings = findings_for(item, updated=dt.date(2026, 10, 20))

    assert rules(findings) == ["stale-updated"]
    assert "R-001" in findings[0].message


def test_unknown_header_key():
    findings = findings_for(make_item("R-001"), sponsor="CMIO")

    assert rules(findings) == ["unknown-field"]


def test_findings_are_sorted_by_line():
    findings = findings_for(
        make_item("R-001", owner=None),
        make_item("I-001", review_by=dt.date(2026, 10, 1), owner=None),
    )
    lines = [f.line for f in findings]
    assert lines == sorted(lines)
