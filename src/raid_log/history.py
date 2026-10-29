"""Read an earlier version of a register from git."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class HistoryError(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    text: str | None
    """File contents at that point, or None if the file did not exist yet."""
    label: str


def read_at(path: Path, ref: str) -> Snapshot:
    """The register as it was at a git ref, or at the end of a YYYY-MM-DD date."""
    if ref.startswith("-"):
        raise HistoryError(f"{ref!r} is not a git ref")
    # Run git next to the file so `<commit>:./name` resolves wherever the repo root is.
    cwd = path.resolve().parent
    name = path.name
    if _try_git(cwd, "rev-parse", "--is-inside-work-tree") is None:
        raise HistoryError(f"{path} is not inside a git repository")

    if _DATE.fullmatch(ref):
        _check_date(ref)
        commit = _git(cwd, "rev-list", "-1", f"--before={ref} 23:59:59", "HEAD", "--", name)
        if not commit.strip():
            return Snapshot(None, f"{ref} (before {name} was first committed)")
    else:
        commit = _try_git(cwd, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if commit is None:
            raise HistoryError(f"unknown git ref {ref!r}")
    commit = commit.strip()

    short, day = _git(cwd, "show", "-s", "--format=%h %cs", commit).split()
    label = f"{short} ({day})" if commit.startswith(ref) else f"{ref} ({short}, {day})"
    if _try_git(cwd, "cat-file", "-e", f"{commit}:./{name}") is None:
        return Snapshot(None, label)
    return Snapshot(_git(cwd, "show", f"{commit}:./{name}"), label)


def _check_date(value: str) -> None:
    # git guesses at dates it cannot parse instead of failing, and its parser stops at 2099.
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        raise HistoryError(f"{value} is not a valid date") from None
    if not 1970 <= day.year <= 2099:
        raise HistoryError(f"{value} is outside the range git can compare dates in")


def _git(cwd: Path, *args: str) -> str:
    result = _run(cwd, args)
    if result.returncode != 0:
        raise HistoryError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def _try_git(cwd: Path, *args: str) -> str | None:
    result = _run(cwd, args)
    return result.stdout if result.returncode == 0 else None


def _run(cwd: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
        )
    except FileNotFoundError:
        raise HistoryError("git is not installed or not on PATH") from None
