"""`raid diff --since` against a throwaway git repository built inside each test."""

import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from raid_log.cli import app
from raid_log.history import HistoryError, read_at

from .factories import make_item, register_text

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Test Runner")
    git(tmp_path, "config", "user.email", "test-runner@example.invalid")
    git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def commit(repo, path, text, message, tag=None):
    path.write_text(text)
    git(repo, "add", str(path.relative_to(repo)))
    git(repo, "commit", "-q", "-m", message)
    if tag:
        git(repo, "tag", tag)


def run_diff(path, since):
    return CliRunner().invoke(app, ["diff", str(path), "--since", since])


def test_diff_since_a_tag_includes_uncommitted_edits(repo):
    register = repo / "raid.yaml"
    commit(repo, register, register_text(make_item("R-001")), "first", tag="steerco-1")
    commit(repo, register, register_text(make_item("R-001"), make_item("I-001")), "add I-001")
    register.write_text(
        register_text(make_item("R-001", owner="Dana Whitfield"), make_item("I-001"))
    )

    result = run_diff(register, "steerco-1")

    assert result.exit_code == 0, result.output
    assert result.output.startswith("Changes to EHR Integration Phase 2 since steerco-1 (")
    assert "New (1)\n  I-001" in result.output
    assert "owner Priya Shah -> Dana Whitfield" in result.output


def test_diff_since_head_shows_only_working_tree_changes(repo):
    register = repo / "raid.yaml"
    commit(repo, register, register_text(make_item("R-001")), "first")

    assert run_diff(register, "HEAD").output.endswith("No changes.\n")


def test_register_in_a_subdirectory(repo):
    (repo / "pm").mkdir()
    register = repo / "pm" / "raid.yaml"
    commit(repo, register, register_text(make_item("R-001")), "first")
    register.write_text(register_text(make_item("R-001"), make_item("D-001")))

    result = run_diff(register, "HEAD")

    assert "New (1)\n  D-001" in result.output


def test_file_missing_at_ref_means_everything_is_new(repo):
    (repo / "README.md").write_text("project notes\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "readme")
    register = repo / "raid.yaml"
    commit(repo, register, register_text(make_item("R-001")), "register")

    result = run_diff(register, "HEAD~1")

    assert "New (1)\n  R-001" in result.output


def test_dates_resolve_to_the_last_commit_by_that_day(repo):
    register = repo / "raid.yaml"
    commit(repo, register, register_text(make_item("R-001")), "first")
    register.write_text(register_text(make_item("R-001"), make_item("R-002")))

    before_history = read_at(register, "2001-01-01")
    assert before_history.text is None
    assert "before raid.yaml was first committed" in before_history.label

    latest = read_at(register, "2099-12-31")
    assert latest.text is not None
    assert "R-002" not in latest.text

    with pytest.raises(HistoryError, match="not a valid date"):
        read_at(register, "2026-13-45")
    with pytest.raises(HistoryError, match="outside the range"):
        read_at(register, "2999-12-31")


def test_unknown_ref_and_non_repo_are_errors(repo, tmp_path_factory):
    register = repo / "raid.yaml"
    commit(repo, register, register_text(make_item("R-001")), "first")

    result = run_diff(register, "no-such-tag")
    assert result.exit_code == 2
    assert "unknown git ref 'no-such-tag'" in result.output

    with pytest.raises(HistoryError, match="not a git ref"):
        read_at(register, "--output=/tmp/x")

    outside = tmp_path_factory.mktemp("plain") / "raid.yaml"
    outside.write_text(register_text(make_item("R-001")))
    with pytest.raises(HistoryError, match="not inside a git repository"):
        read_at(outside, "HEAD")
