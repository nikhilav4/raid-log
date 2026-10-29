import datetime as dt

from typer.testing import CliRunner

from raid_log.cli import app
from raid_log.report import ReportOptions, build_report, to_markdown

from .factories import TODAY, load_items, make_item, register_text

D = dt.date
OPTIONS = ReportOptions(today=TODAY, since=D(2026, 10, 14))


def build(*items, **options):
    register = load_items(*items).register
    return build_report(register, ReportOptions(**{**OPTIONS.__dict__, **options}))


def ids(entries):
    return [getattr(entry, "item", entry).id for entry in entries]


def test_top_risks_by_exposure_then_impact_skipping_closed():
    report = build(
        make_item("R-001", probability=4, impact=3, mitigation="m"),
        make_item("R-002", probability=3, impact=4, mitigation="m"),
        make_item("R-003", probability=5, impact=5, mitigation="m"),
        make_item("R-004", probability=1, impact=1),
        make_item(
            "R-005",
            probability=5,
            impact=5,
            status="closed",
            resolution="Passed",
            log=[{"date": D(2026, 10, 20), "note": "Closed"}],
        ),
        top=3,
    )
    assert ids(report.top_risks) == ["R-003", "R-002", "R-001"]


def test_new_since_is_inclusive_of_the_start_date():
    report = build(
        make_item("R-001", raised=D(2026, 10, 13)),
        make_item("R-002", raised=D(2026, 10, 14)),
        make_item("R-003", raised=D(2026, 10, 27)),
    )
    assert ids(report.new) == ["R-002", "R-003"]


def test_closed_since_uses_the_last_log_entry():
    def closed(item_id, logged):
        log = [{"date": logged, "note": "Closed"}] if logged else None
        return make_item(item_id, status="closed", resolution="Done", log=log)

    report = build(
        closed("I-001", D(2026, 10, 20)),
        closed("I-002", D(2026, 10, 1)),
        closed("I-003", None),
    )
    assert ids(report.closed) == ["I-001"]


def test_overdue_reviews_most_overdue_first():
    report = build(
        make_item("R-001", review_by=D(2026, 10, 27)),
        make_item("R-002", review_by=D(2026, 10, 1)),
        make_item("R-003", review_by=D(2026, 10, 28)),
    )
    assert [(d.item.id, d.days) for d in report.overdue_reviews] == [("R-002", 27), ("R-001", 1)]


def test_aging_issues_by_severity_then_age():
    report = build(
        make_item("I-001", severity="medium", raised=D(2026, 9, 1)),
        make_item("I-002", severity="critical", raised=D(2026, 10, 10)),
        make_item("I-003", severity="critical", raised=D(2026, 10, 1)),
        make_item("I-004", severity="critical", raised=D(2026, 10, 20)),
    )
    assert ids(report.aging_issues) == ["I-003", "I-002", "I-001"]


def test_dependencies_due_include_late_ones():
    report = build(
        make_item("D-001", need_by=D(2026, 11, 11)),
        make_item("D-002", need_by=D(2026, 11, 12)),
        make_item("D-003", need_by=D(2026, 10, 25)),
    )
    assert [(d.item.id, d.days) for d in report.dependencies_due] == [("D-003", -3), ("D-001", 14)]
    assert "| 3 late |" in to_markdown(report)


def test_markdown_escapes_pipes_and_reports_empty_sections():
    text = to_markdown(build(make_item("I-001", title="Lab | radiology interface down")))

    assert "| I-001 | Lab \\| radiology interface down |" in text
    assert "No active risks." in text
    assert "No overdue reviews." in text


def test_report_command_writes_a_file(tmp_path):
    register = tmp_path / "raid.yaml"
    register.write_text(register_text(make_item("R-001", raised=D(2026, 10, 20))))
    out = tmp_path / "status.md"

    result = CliRunner().invoke(
        app, ["report", str(register), "-o", str(out), "--today", "2026-10-28"]
    )

    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert text.startswith("# RAID status: EHR Integration Phase 2")
    assert "Changes counted from 2026-10-14." in text
    assert "R-001 (risk, exposure 6, open)" in text


def test_report_skips_items_with_schema_errors(tmp_path):
    register = tmp_path / "raid.yaml"
    register.write_text(register_text(make_item("R-001"), make_item("R-002", status="paused")))

    result = CliRunner().invoke(app, ["report", str(register), "--today", "2026-10-28"])

    assert result.exit_code == 0
    assert "1 item with schema errors left out" in result.output
