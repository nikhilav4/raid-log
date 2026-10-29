"""Status-meeting report: the parts of the register that need a conversation this week."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from raid_log.model import Item, ItemType, Register


@dataclass(frozen=True)
class ReportOptions:
    today: dt.date
    since: dt.date
    top: int = 5
    due_within: int = 14
    aging_days: int = 14

    @property
    def horizon(self) -> dt.date:
        return self.today + dt.timedelta(days=self.due_within)


@dataclass(frozen=True)
class Dated:
    """An item with the number that makes it worth discussing (days overdue, age, days left)."""

    item: Item
    days: int


@dataclass
class Report:
    register: Register
    options: ReportOptions
    counts: dict[ItemType, tuple[int, int]] = field(default_factory=dict)
    top_risks: list[Item] = field(default_factory=list)
    new: list[Item] = field(default_factory=list)
    closed: list[Item] = field(default_factory=list)
    overdue_reviews: list[Dated] = field(default_factory=list)
    aging_issues: list[Dated] = field(default_factory=list)
    dependencies_due: list[Dated] = field(default_factory=list)
    assumptions_due: list[Dated] = field(default_factory=list)


def build_report(register: Register, options: ReportOptions) -> Report:
    today = options.today
    items = register.items
    active = [item for item in items if item.is_active]
    report = Report(register, options)

    for item_type in ItemType:
        of_type = [item for item in items if item.type is item_type]
        live = sum(item.is_active for item in of_type)
        report.counts[item_type] = (live, len(of_type) - live)

    risks = [item for item in active if item.type is ItemType.RISK and item.exposure]
    risks.sort(key=lambda r: (-(r.exposure or 0), -(r.impact or 0), r.id))
    report.top_risks = risks[: options.top]

    report.new = sorted(
        (item for item in items if options.since <= item.raised <= today),
        key=lambda item: (item.raised, item.id),
    )
    # The format has no closed-on date, so the last log entry stands in for it.
    report.closed = sorted(
        (
            item
            for item in items
            if not item.is_active and item.last_logged and item.last_logged >= options.since
        ),
        key=lambda item: (item.last_logged, item.id),
    )
    report.overdue_reviews = sorted(
        (
            Dated(item, (today - item.review_by).days)
            for item in active
            if item.review_by and item.review_by < today
        ),
        key=lambda d: (-d.days, d.item.id),
    )
    report.aging_issues = sorted(
        (
            Dated(item, (today - item.raised).days)
            for item in active
            if item.type is ItemType.ISSUE and (today - item.raised).days >= options.aging_days
        ),
        key=lambda d: (-(d.item.severity.rank if d.item.severity else 0), -d.days, d.item.id),
    )
    report.dependencies_due = sorted(
        (
            Dated(item, (item.need_by - today).days)
            for item in active
            if item.type is ItemType.DEPENDENCY and item.need_by and item.need_by <= options.horizon
        ),
        key=lambda d: (d.days, d.item.id),
    )
    report.assumptions_due = sorted(
        (
            Dated(item, (item.validate_by - today).days)
            for item in active
            if item.type is ItemType.ASSUMPTION
            and item.validate_by
            and item.validate_by <= options.horizon
        ),
        key=lambda d: (d.days, d.item.id),
    )
    return report


_PLURAL = {
    ItemType.RISK: "Risks",
    ItemType.ASSUMPTION: "Assumptions",
    ItemType.ISSUE: "Issues",
    ItemType.DEPENDENCY: "Dependencies",
}


def to_markdown(report: Report) -> str:
    opts = report.options
    reg = report.register
    updated = f" Register last updated {reg.updated}." if reg.updated else ""
    out = [
        f"# RAID status: {_cell(reg.title)}",
        "",
        f"Report date {opts.today}.{updated} Changes counted from {opts.since}.",
        "",
    ]
    counts = [[_PLURAL[t], str(live), str(done)] for t, (live, done) in report.counts.items()]
    out += _table(["Type", "Active", "Resolved or closed"], counts, align="lrr")

    out += ["## Top risks by exposure", ""]
    out += _table(
        ["ID", "Risk", "P x I", "Exposure", "Owner", "Status", "Review by"],
        [_risk_row(item) for item in report.top_risks],
        align="lllrlll",
        empty="No active risks.",
    )

    out += [f"## New since {opts.since}", ""]
    out += _bullets(
        [
            f"{i.id} ({_kind(i)}, {i.status}) {_cell(i.title)}. "
            f"Owner {_cell(i.owner)}, raised {i.raised}."
            for i in report.new
        ],
        empty="Nothing new.",
    )

    out += [f"## Resolved or closed since {opts.since}", ""]
    out += _bullets(
        [
            f"{i.id} {_cell(i.title)}: {_cell(i.resolution)} ({i.status} {i.last_logged})"
            for i in report.closed
        ],
        empty="Nothing closed.",
    )

    out += ["## Overdue reviews", ""]
    out += _table(
        ["ID", "Title", "Owner", "Review was due", "Days overdue"],
        [
            [*_basics(d.item, "owner"), _date(d.item.review_by), str(d.days)]
            for d in report.overdue_reviews
        ],
        align="llllr",
        empty="No overdue reviews.",
    )

    out += [f"## Issues open {opts.aging_days} days or more", ""]
    out += _table(
        ["ID", "Issue", "Owner", "Severity", "Status", "Age (days)"],
        [
            [*_basics(d.item, "owner"), d.item.severity or "-", d.item.status, str(d.days)]
            for d in report.aging_issues
        ],
        align="lllllr",
        empty="No aging issues.",
    )

    out += [f"## Dependencies due in the next {opts.due_within} days", ""]
    out += _table(
        ["ID", "Dependency", "Counterparty", "Need by", "Days left", "Owner"],
        [
            [
                *_basics(d.item, "counterparty"),
                _date(d.item.need_by),
                _days_left(d.days),
                _cell(d.item.owner),
            ]
            for d in report.dependencies_due
        ],
        align="llllrl",
        empty="No dependencies due.",
    )

    out += [f"## Assumptions to validate in the next {opts.due_within} days", ""]
    out += _table(
        ["ID", "Assumption", "Owner", "Validate by", "Days left"],
        [
            [*_basics(d.item, "owner"), _date(d.item.validate_by), _days_left(d.days)]
            for d in report.assumptions_due
        ],
        align="llllr",
        empty="No assumptions due for validation.",
    )
    return "\n".join(out).rstrip() + "\n"


def _risk_row(risk: Item) -> list[str]:
    return [
        risk.id,
        _cell(risk.title),
        f"{risk.probability} x {risk.impact}",
        str(risk.exposure),
        _cell(risk.owner),
        risk.status,
        _date(risk.review_by),
    ]


def _kind(item: Item) -> str:
    if item.exposure:
        return f"{item.type}, exposure {item.exposure}"
    if item.severity:
        return f"{item.type}, {item.severity}"
    return str(item.type)


def _basics(item: Item, third: str) -> list[str]:
    return [item.id, _cell(item.title), _cell(getattr(item, third))]


def _table(
    headers: list[str], rows: list[list[str]], align: str, empty: str | None = None
) -> list[str]:
    if not rows and empty:
        return [empty, ""]
    rule = ["---:" if a == "r" else "---" for a in align]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(rule) + " |"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return [*lines, ""]


def _bullets(lines: list[str], empty: str) -> list[str]:
    if not lines:
        return [empty, ""]
    return [*(f"- {line}" for line in lines), ""]


def _cell(text: str | None) -> str:
    if not text:
        return "-"
    return " ".join(text.split()).replace("|", "\\|")


def _date(value: dt.date | None) -> str:
    return str(value) if value else "-"


def _days_left(days: int) -> str:
    return f"{-days} late" if days < 0 else str(days)
