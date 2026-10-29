import datetime as dt

from typer.testing import CliRunner

from raid_log.cli import app
from raid_log.diff import compare, to_markdown, to_text

from .factories import load_items, make_item, register_text

D = dt.date
CLOSED = {
    "status": "closed",
    "resolution": "Vendor delivered the feed",
    "log": [{"date": D(2026, 10, 20), "note": "Feed live in test"}],
}


def registers(before, after):
    return load_items(*before).register, load_items(*after).register


def section(diff, heading):
    return [c.after.id for c in dict(diff.sections())[heading]]


def test_added_removed_and_unchanged():
    before, after = registers(
        [make_item("R-001"), make_item("R-002")],
        [make_item("R-001"), make_item("R-003")],
    )
    diff = compare(before, after)

    assert [i.id for i in diff.added] == ["R-003"]
    assert [i.id for i in diff.removed] == ["R-002"]
    assert diff.changed == []


def test_changes_are_grouped_for_steering():
    before, after = registers(
        [
            make_item("R-001", probability=3, impact=3),
            make_item("R-002", probability=4, impact=3, mitigation="m"),
            make_item("R-003"),
            make_item("D-001"),
            make_item("I-001", status="resolved", resolution="Fixed", log=CLOSED["log"]),
        ],
        [
            make_item("R-001", probability=4, impact=3, mitigation="m"),
            make_item("R-002", probability=2, impact=3, mitigation="m"),
            make_item("R-003", **CLOSED),
            make_item("D-001", need_by=D(2026, 11, 30)),
            make_item("I-001", status="open", resolution="Fixed", log=CLOSED["log"]),
        ],
    )
    diff = compare(before, after)

    assert section(diff, "Exposure up") == ["R-001"]
    assert section(diff, "Exposure down") == ["R-002"]
    assert section(diff, "Resolved or closed") == ["R-003"]
    assert section(diff, "Reopened") == ["I-001"]
    assert section(diff, "Other changes") == ["D-001"]


def test_change_lines_fold_rating_into_exposure_and_list_new_notes():
    before, after = registers(
        [make_item("R-001", probability=3, impact=5, mitigation="Weekly checkpoint")],
        [
            make_item(
                "R-001",
                probability=4,
                impact=5,
                status="mitigating",
                mitigation="Weekly checkpoint; flat-file fallback scoped",
                log=[{"date": D(2026, 10, 24), "note": "Test feed slipped to 11-04"}],
            )
        ],
    )
    text = to_text(compare(before, after), "EHR Integration Phase 2", "steerco")

    assert text == (
        "Changes to EHR Integration Phase 2 since steerco\n"
        "\n"
        "Exposure up (1)\n"
        "  R-001  Title for R-001\n"
        "         exposure 15 -> 20 (probability 3 -> 4)\n"
        "         status open -> mitigating\n"
        "         mitigation changed: Weekly checkpoint; flat-file fallback scoped\n"
        "         note 2026-10-24: Test feed slipped to 11-04\n"
    )


def test_closed_item_shows_resolution_once():
    before, after = registers([make_item("R-001")], [make_item("R-001", **CLOSED)])

    text = to_text(compare(before, after), "P", "x")

    assert "open -> closed: Vendor delivered the feed" in text
    assert "resolution" not in text
    assert "note 2026-10-20: Feed live in test" in text


def test_markdown_and_empty_diff():
    before, after = registers([make_item("R-001")], [make_item("R-001"), make_item("I-001")])

    md = to_markdown(compare(before, after), "P", "x")
    assert "### New (1)" in md
    assert "- **I-001** Title for I-001\n  - issue, medium, open, owner Priya Shah" in md

    same = to_text(compare(after, after), "P", "x")
    assert same.endswith("No changes.\n")


def test_everything_is_new_without_a_previous_version():
    _, after = registers([], [make_item("R-001")])

    assert [i.id for i in compare(None, after).added] == ["R-001"]


def test_against_compares_two_files(tmp_path):
    old = tmp_path / "old.yaml"
    new = tmp_path / "raid.yaml"
    old.write_text(register_text(make_item("R-001")))
    new.write_text(register_text(make_item("R-001", owner="Marcus Bell")))

    result = CliRunner().invoke(app, ["diff", str(new), "--against", str(old)])

    assert result.exit_code == 0, result.output
    assert "owner Priya Shah -> Marcus Bell" in result.output


def test_diff_needs_exactly_one_baseline(tmp_path):
    path = tmp_path / "raid.yaml"
    path.write_text(register_text(make_item("R-001")))
    runner = CliRunner()

    assert runner.invoke(app, ["diff", str(path)]).exit_code == 2
    both = runner.invoke(app, ["diff", str(path), "--since", "HEAD", "--against", str(path)])
    assert both.exit_code == 2
