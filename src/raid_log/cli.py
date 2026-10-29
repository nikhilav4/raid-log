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
from raid_log.report import ReportOptions, build_report, to_markdown
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


class ReportFormat(StrEnum):
    MARKDOWN = "markdown"


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


@app.command()
def report(
    register: RegisterArg = DEFAULT_REGISTER,
    since: Annotated[
        dt.datetime | None,
        typer.Option(
            formats=["%Y-%m-%d"],
            metavar="YYYY-MM-DD",
            help="First day counted as new or closed, usually the last steering meeting. "
            "Defaults to 14 days before today.",
            show_default=False,
        ),
    ] = None,
    top: Annotated[int, typer.Option(min=1, help="How many risks to list.")] = 5,
    due_within: Annotated[
        int, typer.Option(min=0, help="Days ahead to look for dependencies and assumptions.")
    ] = 14,
    aging_days: Annotated[
        int, typer.Option(min=0, help="Age at which an open issue counts as aging.")
    ] = 14,
    output_format: Annotated[
        ReportFormat, typer.Option("--format", help="Output format.")
    ] = ReportFormat.MARKDOWN,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write to a file instead of stdout.")
    ] = None,
    today: TodayOption = None,
) -> None:
    """Status report: top risks, what changed, overdue reviews, aging issues, due dates."""
    loaded = _load_or_exit(register)
    as_of = _as_date(today)
    options = ReportOptions(
        today=as_of,
        since=since.date() if since else as_of - dt.timedelta(days=14),
        top=top,
        due_within=due_within,
        aging_days=aging_days,
    )
    text = to_markdown(build_report(loaded.register, options))
    _write(text, output)


@app.command()
def heatmap(
    register: RegisterArg = DEFAULT_REGISTER,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Image to write, .png or .svg.")
    ] = Path("raid-heatmap.png"),
    include_closed: Annotated[
        bool, typer.Option("--include-closed", help="Plot resolved and closed risks too.")
    ] = False,
    today: TodayOption = None,
) -> None:
    """5x5 probability by impact heatmap with risk IDs in their cells."""
    if output.suffix.lower() not in (".png", ".svg"):
        typer.echo("error: --output must end in .png or .svg", err=True)
        raise typer.Exit(2)
    loaded = _load_or_exit(register)
    # matplotlib takes a moment to import, so only commands that draw pay for it.
    from raid_log import heatmap as grid

    fig = grid.draw(loaded.register, _as_date(today), include_closed)
    grid.save(fig, output)
    count = len(grid.plotted_risks(loaded.register, include_closed))
    typer.echo(f"wrote {output} ({_plural(count, 'risk')})", err=True)


def _load_or_exit(path: Path) -> Loaded:
    try:
        loaded = load(path)
    except RegisterError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from None
    if loaded.skipped:
        typer.echo(
            f"note: {_plural(loaded.skipped, 'item')} with schema errors left out; "
            f"run `raid validate {path}` for details",
            err=True,
        )
    return loaded


def _write(text: str, output: Path | None) -> None:
    if output is None:
        typer.echo(text, nl=False)
    else:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {output}", err=True)


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
