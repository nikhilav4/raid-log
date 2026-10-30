"""Adding items to a register file."""

from __future__ import annotations

import re
from collections.abc import Iterable

from raid_log.model import ItemType


def next_id(raw_ids: Iterable[str | None], item_type: ItemType) -> str:
    """One past the highest ID of this type, padded like the widest existing one."""
    pattern = re.compile(rf"{item_type.prefix}-(\d+)")
    digits = [m[1] for raw_id in raw_ids if raw_id and (m := pattern.fullmatch(raw_id))]
    # Gaps are never filled: a deleted ID may still be quoted in old minutes and emails.
    highest = max((int(d) for d in digits), default=0)
    width = max([3, *(len(d) for d in digits)])
    return f"{item_type.prefix}-{highest + 1:0{width}d}"
