from __future__ import annotations

import datetime as dt
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from raid_log import __version__
from raid_log.findings import Finding, Level, as_dict, github_annotation
from raid_log.loader import Loaded, RegisterError, load
from raid_log.rules import validate as run_rules

app = typer.Typer(
    help="Validate, report on and diff a RAID register kept as YAML.",
    no_args_is_help=True,
    add_completion=False,
)

DEFAULT_REGISTER = Path("raid.yaml")

RegisterArg = Annotated[
    Path, typer.Argument(help="Register file.", dir_okay=False, show_default=True)
]
TodayOption = Annotated[
    dt.datetime | None,
    typer.Option(
        formats=["%Y-%m-%d"],
        metavar="YYYY-MM-DD",
        help="Date to treat as today. Defaults to the system date.",
        show_default=False,
    ),
]


class ValidateFormat(StrEnum):
    TEXT = "text"
    GITHUB = "github"
    JSON = "json"


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"raid-log {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    """Validate, report on and diff a RAID register kept as YAML."""


@app.command()
def validate(
    registers: Annotated[
        list[Path] | None,
        typer.Argument(help="Register files. [default: raid.yaml]", show_default=False),
    ] = None,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit non-zero on warnings as well as errors.")
    ] = False,
    output: Annotated[
        ValidateFormat,
        typer.Option("--format", help="text for people, github for PR annotations, or json."),
    ] = ValidateFormat.TEXT,
    today: TodayOption = None,
) -> None:
    """Check registers against the shared format and the RAID rules."""
    as_of = _as_date(today)
    exit_code = 0
    json_out: list[dict[str, object]] = []
    for path in registers or [DEFAULT_REGISTER]:
        try:
            loaded = load(path)
        except RegisterError as exc:
            _report_unreadable(str(path), str(exc), output)
            exit_code = 2
            continue
        findings = run_rules(loaded, as_of)
        if output is ValidateFormat.JSON:
            json_out.extend(as_dict(str(path), f) for f in findings)
        else:
            _print_findings(loaded, findings, output)
        errors = sum(f.is_error for f in findings)
        if errors or (strict and findings):
            exit_code = max(exit_code, 1)
    if output is ValidateFormat.JSON:
        typer.echo(json.dumps(json_out, indent=2))
    raise typer.Exit(exit_code)


def _print_findings(loaded: Loaded, findings: list[Finding], output: ValidateFormat) -> None:
    path = str(loaded.path)
    for finding in findings:
        if output is ValidateFormat.GITHUB:
            typer.echo(github_annotation(path, finding))
            continue
        where = f"{path}:{finding.line}" if finding.line else path
        color = "red" if finding.level is Level.ERROR else "yellow"
        level = typer.style(str(finding.level), fg=color, bold=True)
        item = f"{finding.item_id}: " if finding.item_id else ""
        rule = typer.style(f"[{finding.rule}]", dim=True)
        typer.echo(f"{where}: {level} {item}{finding.message} {rule}")
    typer.echo(_summary(loaded, findings))


def _summary(loaded: Loaded, findings: list[Finding]) -> str:
    errors = sum(f.is_error for f in findings)
    warnings = len(findings) - errors
    items = _plural(len(loaded.raw), "item")
    if not findings:
        return f"{loaded.path}: {items}, no problems"
    return f"{loaded.path}: {items}, {_plural(errors, 'error')}, {_plural(warnings, 'warning')}"


def _report_unreadable(path: str, message: str, output: ValidateFormat) -> None:
    if output is ValidateFormat.GITHUB:
        first_line = message.splitlines()[0]
        typer.echo(github_annotation(path, Finding(Level.ERROR, "unreadable", first_line)))
    typer.echo(f"error: {message}", err=True)


def _as_date(value: dt.datetime | None) -> dt.date:
    return value.date() if value else dt.date.today()


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
