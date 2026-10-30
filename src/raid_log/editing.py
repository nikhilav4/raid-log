"""Adding items to a register file without disturbing the rest of it."""

from __future__ import annotations

import datetime as dt
import io
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.representer import RoundTripRepresenter

from raid_log.loader import Loaded, parse, yaml_round_trip
from raid_log.model import ItemType

# The shared format's field order, with the type-specific fields after review_by, so an added
# item reads like the hand-written ones around it.
_FIELD_ORDER = (
    "id",
    "type",
    "title",
    "description",
    "owner",
    "status",
    "raised",
    "review_by",
    "probability",
    "impact",
    "severity",
    "counterparty",
    "need_by",
    "validate_by",
    "mitigation",
    "contingency",
    "workstream",
    "links",
    "tags",
    "source",
)


@dataclass(frozen=True)
class Added:
    item_id: str
    text: str
    """The whole register with the new item appended."""


def next_id(raw_ids: Iterable[str | None], item_type: ItemType) -> str:
    """One past the highest ID of this type, padded like the widest existing one."""
    pattern = re.compile(rf"{item_type.prefix}-(\d+)")
    digits = [m[1] for raw_id in raw_ids if raw_id and (m := pattern.fullmatch(raw_id))]
    # Gaps are never filled: a deleted ID may still be quoted in old minutes and emails.
    highest = max((int(d) for d in digits), default=0)
    width = max([3, *(len(d) for d in digits)])
    return f"{item_type.prefix}-{highest + 1:0{width}d}"


def add_item(
    text: str, path: Path, item_type: ItemType, fields: Mapping[str, Any], today: dt.date
) -> Added:
    """Append an item with the next free ID and set `updated` to today.

    Comments, quoting and blank lines in the rest of the file stay as they were. Raises
    `RegisterError` if the text cannot be read as a register.
    """
    loaded = parse(text, path)
    item_id = next_id((entry.item_id for entry in loaded.raw), item_type)

    yaml = _round_trip()
    data = yaml.load(text) or CommentedMap()
    items = data.get("items")
    if not isinstance(items, list):
        items = data["items"] = CommentedSeq()
    # `items: []` loads as a flow sequence and would put the new item on that same line.
    items.fa.set_block_style()
    items.append(_new_item({"id": item_id, "type": item_type, **fields}))
    if _blank_line_between_items(text, loaded):
        items.yaml_set_comment_before_after_key(len(items) - 1, before="\n")
    _set_updated(data, today)

    stream = io.StringIO()
    yaml.dump(data, stream)
    return Added(item_id, stream.getvalue())


class _Representer(RoundTripRepresenter):
    def ignore_aliases(self, data: Any) -> bool:
        # A new item's `raised` is usually the same date object as `updated`. Write the date
        # twice rather than as a YAML anchor and alias.
        return isinstance(data, dt.date) or super().ignore_aliases(data)


def _round_trip() -> YAML:
    # With these settings the example register dumps back byte for byte.
    yaml = yaml_round_trip()
    yaml.Representer = _Representer
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    yaml.preserve_quotes = True
    return yaml


def _new_item(fields: Mapping[str, Any]) -> CommentedMap:
    item = CommentedMap()
    for key in sorted(fields, key=_FIELD_ORDER.index):
        value = fields[key]
        if isinstance(value, Enum):
            value = value.value
        if isinstance(value, str):
            # Blank text means not given, as it does when the register is loaded.
            value = value.strip() or None
        if isinstance(value, list):
            value = _flow(value) if value else None
        if value is not None:
            item[key] = value
    return item


def _flow(values: list[Any]) -> CommentedSeq:
    # `links: [D-003]` on one line, the way registers are written by hand.
    seq = CommentedSeq(values)
    seq.fa.set_flow_style()
    return seq


def _blank_line_between_items(text: str, loaded: Loaded) -> bool:
    # Follow the file's own spacing, judged by its last two items, so a register written with
    # blank lines between items does not get one item squashed against the one above.
    if len(loaded.raw) < 2:
        return False
    start, end = loaded.raw[-2].line, loaded.raw[-1].line
    if start is None or end is None:
        return False
    return any(not line.strip() for line in text.splitlines()[start - 1 : end - 1])


def _set_updated(data: CommentedMap, today: dt.date) -> None:
    if "updated" in data:
        data["updated"] = today
        return
    keys = list(data)
    data.insert(keys.index("project") + 1 if "project" in keys else 0, "updated", today)
