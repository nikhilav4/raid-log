import datetime as dt

from typer.testing import CliRunner

from raid_log import heatmap
from raid_log.cli import app

from .factories import TODAY, load_items, make_item, register_text


def risks(count, probability=3, impact=3):
    return [
        make_item(f"R-{n:03d}", probability=probability, impact=impact, mitigation="m")
        for n in range(1, count + 1)
    ]


def test_band_colors_follow_exposure_floors():
    assert heatmap.band_color(25) == heatmap.band_color(20)
    assert heatmap.band_color(16) == heatmap.band_color(12)
    assert heatmap.band_color(10) == heatmap.band_color(5)
    assert heatmap.band_color(4) == heatmap.band_color(1)
    assert len({heatmap.band_color(e) for e in (1, 5, 12, 20)}) == 4


def test_cell_label_wraps_and_truncates():
    assert heatmap._wrap(["R-001"]) == "R-001"
    assert heatmap._wrap(["R-001", "R-002", "R-003"]) == "R-001  R-002\nR-003"

    eight = [f"R-{n:03d}" for n in range(1, 9)]
    assert heatmap._wrap(eight).count("\n") == 3
    nine = [f"R-{n:03d}" for n in range(1, 10)]
    assert heatmap._wrap(nine).splitlines()[-1] == "+3 more"


def test_only_active_risks_are_plotted_by_default():
    register = load_items(
        make_item("R-001"),
        make_item(
            "R-002",
            status="closed",
            resolution="Passed",
            log=[{"date": dt.date(2026, 10, 20), "note": "Closed"}],
        ),
        make_item("I-001"),
    ).register

    assert [r.id for r in heatmap.plotted_risks(register)] == ["R-001"]
    assert [r.id for r in heatmap.plotted_risks(register, include_closed=True)] == [
        "R-001",
        "R-002",
    ]


def test_svg_is_repeatable_and_keeps_ids_as_text():
    register = load_items(*risks(3)).register

    first = heatmap.to_svg(heatmap.draw(register, TODAY))
    second = heatmap.to_svg(heatmap.draw(register, TODAY))

    assert first == second
    assert "R-001  R-002" in first
    assert "3 active risks as of 2026-10-28" in first


def test_heatmap_command_writes_png_and_svg(tmp_path):
    register = tmp_path / "raid.yaml"
    register.write_text(register_text(*risks(2)))
    runner = CliRunner()

    png = tmp_path / "grid.png"
    result = runner.invoke(app, ["heatmap", str(register), "-o", str(png)])
    assert result.exit_code == 0, result.output
    assert png.read_bytes().startswith(b"\x89PNG")
    assert "2 risks" in result.output

    svg = tmp_path / "grid.svg"
    assert runner.invoke(app, ["heatmap", str(register), "-o", str(svg)]).exit_code == 0
    assert svg.read_text().lstrip().startswith("<?xml")


def test_heatmap_rejects_other_formats(tmp_path):
    register = tmp_path / "raid.yaml"
    register.write_text(register_text(*risks(1)))

    result = CliRunner().invoke(app, ["heatmap", str(register), "-o", str(tmp_path / "x.jpg")])

    assert result.exit_code == 2
    assert ".png or .svg" in result.output
