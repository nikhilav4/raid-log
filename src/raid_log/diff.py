"""What changed between two versions of a register, grouped the way a steering meeting reads it."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from raid_log.model import Item, ItemType, LogEntry, Register

_COMPARED = [name for name in Item.model_fields if name not in ("id", "log")]
# Prose fields are summarised ("mitigation changed: ...") rather than shown before and after.
_PROSE = {"description", "mitigation", "contingency", "resolution"}


@dataclass(frozen=True)
class FieldChange:
    name: str
    before: object
    after: object


@dataclass(frozen=True)
class ItemChange:
    before: Item
    after: Item
    fields: list[FieldChange]
    new_notes: list[LogEntry]

    @property
    def exposure_delta(self) -> int:
        if self.before.exposure is None or self.after.exposure is None:
            return 0
        return self.after.exposure - self.before.exposure

    @property
    def closed(self) -> bool:
        return self.before.is_active and not self.after.is_active

    @property
    def reopened(self) -> bool:
        return not self.before.is_active and self.after.is_active


@dataclass
class RegisterDiff:
    added: list[Item] = field(default_factory=list)
    removed: list[Item] = field(default_factory=list)
    changed: list[ItemChange] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def sections(self) -> list[tuple[str, list[ItemChange]]]:
        closed = [c for c in self.changed if c.closed]
        reopened = [c for c in self.changed if c.reopened]
        live = [c for c in self.changed if not c.closed and not c.reopened]
        up = [c for c in live if c.exposure_delta > 0]
        down = [c for c in live if c.exposure_delta < 0]
        other = [c for c in live if c.exposure_delta == 0]
        return [
            ("Resolved or closed", closed),
            ("Reopened", reopened),
            ("Exposure up", up),
            ("Exposure down", down),
            ("Other changes", other),
        ]


def compare(before: Register | None, after: Register) -> RegisterDiff:
    old = {item.id: item for item in before.items} if before else {}
    new = {item.id: item for item in after.items}
    result = RegisterDiff(
        added=[item for item_id, item in new.items() if item_id not in old],
        removed=[item for item_id, item in old.items() if item_id not in new],
    )
    for item_id, item in new.items():
        if item_id in old and (change := _compare_item(old[item_id], item)):
            result.changed.append(change)
    return result


def _compare_item(before: Item, after: Item) -> ItemChange | None:
    old = before.model_dump(include=set(_COMPARED))
    new = after.model_dump(include=set(_COMPARED))
    fields = [
        FieldChange(name, old[name], new[name]) for name in _COMPARED if old[name] != new[name]
    ]
    seen = {(entry.date, entry.note) for entry in before.log}
    notes = [entry for entry in after.log if (entry.date, entry.note) not in seen]
    if not fields and not notes:
        return None
    return ItemChange(before, after, fields, notes)


def change_lines(change: ItemChange) -> list[str]:
    """One line per change, with probability and impact folded into an exposure line."""
    lines = []
    if change.closed:
        resolution = change.after.resolution
        lines.append(
            f"{change.before.status} -> {change.after.status}"
            + (f": {resolution}" if resolution else ", no resolution recorded")
        )
    rated = {"probability", "impact"}
    names = {f.name for f in change.fields}
    if change.after.type is ItemType.RISK and names & rated and change.exposure_delta:
        parts = [
            f"{f.name} {_value(f.before)} -> {_value(f.after)}"
            for f in change.fields
            if f.name in rated
        ]
        lines.append(
            f"exposure {change.before.exposure} -> {change.after.exposure} ({', '.join(parts)})"
        )
        names -= rated
    for f in change.fields:
        if f.name not in names or (change.closed and f.name in ("status", "resolution")):
            continue
        if f.name in _PROSE:
            verb = "added" if f.before is None else "removed" if f.after is None else "changed"
            lines.append(f"{f.name} {verb}" + (f": {f.after}" if f.after is not None else ""))
        else:
            lines.append(f"{f.name} {_value(f.before)} -> {_value(f.after)}")
    lines += [f"note {entry.date}: {entry.note}" for entry in change.new_notes]
    return lines


def added_line(item: Item) -> str:
    parts = [str(item.type)]
    if item.exposure is not None:
        parts.append(f"exposure {item.exposure}")
    if item.severity is not None:
        parts.append(str(item.severity))
    parts += [str(item.status), f"owner {item.owner or 'not set'}"]
    return ", ".join(parts)


def to_text(diff: RegisterDiff, project: str, since_label: str) -> str:
    out = [f"Changes to {project} since {since_label}", ""]
    if diff.is_empty:
        return "\n".join([*out, "No changes."]) + "\n"
    for heading, entries in _blocks(diff):
        out.append(f"{heading} ({len(entries)})")
        for item, details in entries:
            out.append(f"  {item.id}  {item.title}")
            out += [f"         {line}" for line in details]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def to_markdown(diff: RegisterDiff, project: str, since_label: str) -> str:
    out = [f"## Changes to {project} since {since_label}", ""]
    if diff.is_empty:
        return "\n".join([*out, "No changes."]) + "\n"
    for heading, entries in _blocks(diff):
        out += [f"### {heading} ({len(entries)})", ""]
        for item, details in entries:
            out.append(f"- **{item.id}** {item.title}")
            out += [f"  - {line}" for line in details]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _blocks(diff: RegisterDiff) -> list[tuple[str, list[tuple[Item, list[str]]]]]:
    blocks: list[tuple[str, list[tuple[Item, list[str]]]]] = []
    if diff.added:
        blocks.append(("New", [(item, [added_line(item)]) for item in diff.added]))
    for heading, changes in diff.sections():
        if changes:
            blocks.append((heading, [(c.after, change_lines(c)) for c in changes]))
    if diff.removed:
        note = "deleted from the register; close items instead so the history stays"
        blocks.append(("Removed", [(item, [note]) for item in diff.removed]))
    return blocks


def _value(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)
