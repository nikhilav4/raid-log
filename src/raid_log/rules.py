"""Integrity and hygiene rules for a loaded register.

Errors are problems with the register itself. Warnings are mostly things that go stale with the
calendar (an overdue review, a need-by date that has passed), kept separate so a register that was
valid when it was merged does not start failing CI on its own a week later.
"""

from __future__ import annotations

import datetime as dt
import difflib
from collections.abc import Iterator

from raid_log.findings import Finding, Level, error, warning
from raid_log.loader import Loaded, Located
from raid_log.model import TYPE_SPECIFIC_FIELDS, Item, ItemType, Register

HIGH_EXPOSURE = 12

_ITEM_FIELDS = sorted(Item.model_fields)
_HEADER_FIELDS = sorted(Register.model_fields)


def validate(loaded: Loaded, today: dt.date) -> list[Finding]:
    findings = [*loaded.findings, *_check_header(loaded), *_check_duplicate_ids(loaded)]
    known_ids = {entry.item_id for entry in loaded.raw if entry.item_id}
    for located in loaded.located:
        findings.extend(_check_item(located, known_ids, today))
    return sorted(findings, key=lambda f: (f.line or 0, f.level is not Level.ERROR))


def _check_header(loaded: Loaded) -> Iterator[Finding]:
    register, lines = loaded.register, loaded.header_lines
    for key in register.model_extra or {}:
        yield warning("unknown-field", _unknown(key, _HEADER_FIELDS), line=lines.get(key))
    if register.updated is not None:
        latest = max(((item.last_activity, item.id) for item in register.items), default=None)
        if latest and latest[0] > register.updated:
            yield warning(
                "stale-updated",
                f"`updated` is {register.updated} but {latest[1]} has an entry dated "
                f"{latest[0]}; bump `updated` when you edit the register",
                line=lines.get("updated"),
            )


def _check_duplicate_ids(loaded: Loaded) -> Iterator[Finding]:
    first_seen: dict[str, int | None] = {}
    for entry in loaded.raw:
        if entry.item_id is None:
            continue
        if entry.item_id in first_seen:
            first = first_seen[entry.item_id]
            where = f" (first used on line {first})" if first else ""
            yield error(
                "duplicate-id",
                f"{entry.item_id} is used more than once{where}",
                entry.item_id,
                entry.line,
            )
        else:
            first_seen[entry.item_id] = entry.line


def _check_item(located: Located, known_ids: set[str], today: dt.date) -> Iterator[Finding]:
    item = located.item

    def err(rule: str, message: str, key: str = "id") -> Finding:
        return error(rule, message, item.id, located.line_of(key))

    def warn(rule: str, message: str, key: str = "id") -> Finding:
        return warning(rule, message, item.id, located.line_of(key))

    if item.id[0] != item.type.prefix:
        yield err("id-prefix", f"{item.type} IDs start with {item.type.prefix}-")
    if item.owner is None:
        yield err("missing-owner", "no owner; every item needs a named owner", "owner")

    for link in item.links:
        if link == item.id:
            yield warn("self-link", "links to itself", "links")
        elif link not in known_ids:
            yield err("broken-link", f"links to {link}, which is not in the register", "links")

    if item.is_active:
        if item.review_by is None:
            yield err("missing-review-date", f"{item.status} item has no review_by date")
        elif item.review_by < today:
            yield warn(
                "review-overdue",
                f"review was due {item.review_by} ({_days(today - item.review_by)} ago)",
                "review_by",
            )
    else:
        if item.resolution is None:
            yield err("missing-resolution", f"{item.status} but no resolution recorded", "status")
        if not item.log:
            yield warn(
                "undated-closure",
                f"{item.status} with no log entry, so reports cannot tell when it closed",
                "status",
            )

    if item.review_by is not None and item.review_by < item.raised:
        yield warn("date-order", f"review_by {item.review_by} is before raised", "review_by")

    yield from _check_type_fields(item, located, today)

    for key in item.model_extra or {}:
        yield warn("unknown-field", _unknown(key, _ITEM_FIELDS), key)
    for name, owner_type in TYPE_SPECIFIC_FIELDS.items():
        if owner_type is not item.type and getattr(item, name) is not None:
            yield warn(
                "wrong-type-field",
                f"{name} only applies to {owner_type}s and is ignored here",
                name,
            )


def _check_type_fields(item: Item, located: Located, today: dt.date) -> Iterator[Finding]:
    line_of = located.line_of
    match item.type:
        case ItemType.RISK:
            if item.exposure is None:
                yield error(
                    "missing-rating",
                    "risk needs probability and impact (1-5)",
                    item.id,
                    line_of("id"),
                )
            elif item.is_active and item.exposure >= HIGH_EXPOSURE and item.mitigation is None:
                yield error(
                    "unmitigated-risk",
                    f"exposure {item.exposure} ({item.probability} x {item.impact}) "
                    "needs a mitigation",
                    item.id,
                    line_of("probability"),
                )
        case ItemType.ISSUE:
            if item.severity is None:
                yield warning("missing-severity", "issue has no severity", item.id, line_of("id"))
        case ItemType.DEPENDENCY:
            missing = [f for f in ("counterparty", "need_by") if getattr(item, f) is None]
            if missing:
                yield error(
                    "dependency-details",
                    f"dependency has no {' or '.join(missing)}",
                    item.id,
                    line_of("id"),
                )
            if item.need_by is not None and item.is_active and item.need_by < today:
                yield warning(
                    "need-by-passed",
                    f"needed by {item.need_by} ({_days(today - item.need_by)} ago) and still open",
                    item.id,
                    line_of("need_by"),
                )
        case ItemType.ASSUMPTION:
            if item.is_active and item.validate_by is None:
                yield warning(
                    "missing-validate-by",
                    "assumption has no validate_by date",
                    item.id,
                    line_of("id"),
                )
            elif item.is_active and item.validate_by is not None and item.validate_by < today:
                yield warning(
                    "validate-by-passed",
                    f"should have been validated by {item.validate_by}; confirm it or raise a risk",
                    item.id,
                    line_of("validate_by"),
                )


def _unknown(key: str, known: list[str]) -> str:
    match = difflib.get_close_matches(key, known, n=1)
    hint = f"; did you mean `{match[0]}`?" if match else ""
    return f"unknown field `{key}`{hint}"


def _days(delta: dt.timedelta) -> str:
    return "1 day" if delta.days == 1 else f"{delta.days} days"
