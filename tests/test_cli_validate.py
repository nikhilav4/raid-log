import datetime as dt
import json

from typer.testing import CliRunner

from raid_log.cli import app

from .factories import make_item, register_text

runner = CliRunner()


def write(tmp_path, *items, name="raid.yaml"):
    path = tmp_path / name
    path.write_text(register_text(*items))
    return path


def run(*args):
    return runner.invoke(app, [*args, "--today", "2026-10-28"])


def test_clean_register_exits_zero(tmp_path):
    path = write(tmp_path, make_item("R-001"), make_item("D-001"))

    result = run("validate", str(path))

    assert result.exit_code == 0
    assert result.output.strip() == f"{path}: 2 items, no problems"


def test_errors_exit_one_and_name_file_line_and_item(tmp_path):
    path = write(tmp_path, make_item("R-001", probability=4, impact=4))

    result = run("validate", str(path))

    assert result.exit_code == 1
    assert f"{path}:" in result.output
    assert "error R-001: exposure 16 (4 x 4) needs a mitigation [unmitigated-risk]" in result.output
    assert "1 item, 1 error, 0 warnings" in result.output


def test_warnings_only_fail_with_strict(tmp_path):
    path = write(tmp_path, make_item("I-001", review_by=dt.date(2026, 10, 1)))

    assert run("validate", str(path)).exit_code == 0
    assert run("validate", str(path), "--strict").exit_code == 1


def test_missing_file_exits_two(tmp_path):
    result = run("validate", str(tmp_path / "nope.yaml"))

    assert result.exit_code == 2
    assert "no such file" in result.output


def test_worst_result_wins_across_files(tmp_path):
    good = write(tmp_path, make_item("R-001"), name="good.yaml")
    bad = write(tmp_path, make_item("R-001", owner=None), name="bad.yaml")

    result = run("validate", str(good), str(bad))

    assert result.exit_code == 1
    assert "good.yaml: 1 item, no problems" in result.output


def test_github_format_emits_annotations(tmp_path):
    path = write(tmp_path, make_item("R-001", owner=None))

    result = run("validate", str(path), "--format", "github")

    first = result.output.splitlines()[0]
    assert first.startswith(f"::error file={path},line=")
    assert first.endswith("::R-001: no owner; every item needs a named owner")


def test_json_format(tmp_path):
    path = write(tmp_path, make_item("R-001", owner=None))

    result = run("validate", str(path), "--format", "json")

    assert result.exit_code == 1
    (finding,) = json.loads(result.output)
    assert finding["rule"] == "missing-owner"
    assert finding["item"] == "R-001"
    assert finding["level"] == "error"
