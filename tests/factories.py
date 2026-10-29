from __future__ import annotations

import datetime as dt
import io
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from raid_log.loader import Loaded, parse

TODAY = dt.date(2026, 10, 28)

_TYPES = {"R": "risk", "A": "assumption", "I": "issue", "D": "dependency"}
_TYPE_DEFAULTS: dict[str, dict[str, Any]] = {
    "risk": {"probability": 2, "impact": 3},
    "issue": {"severity": "medium"},
    "dependency": {"counterparty": "Hospital IT interface team", "need_by": dt.date(2026, 11, 15)},
    "assumption": {"validate_by": dt.date(2026, 11, 5)},
}


def make_item(item_id: str, **overrides: Any) -> dict[str, Any]:
    """A valid item of the type implied by the ID prefix; pass field=None to drop a field."""
    item_type = overrides.get("type", _TYPES[item_id[0]])
    data: dict[str, Any] = {
        "id": item_id,
        "type": item_type,
        "title": f"Title for {item_id}",
        "owner": "Priya Shah",
        "status": "open",
        "raised": dt.date(2026, 10, 1),
        "review_by": dt.date(2026, 11, 5),
        **_TYPE_DEFAULTS[item_type],
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def dump(data: Any) -> str:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    stream = io.StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()


def register_text(*items: dict[str, Any], **header: Any) -> str:
    data = {
        "project": "EHR Integration Phase 2",
        "updated": dt.date(2026, 10, 27),
        **header,
        "items": list(items),
    }
    return dump({key: value for key, value in data.items() if value is not None})


def load_items(*items: dict[str, Any], **header: Any) -> Loaded:
    return parse(register_text(*items, **header), Path("raid.yaml"))
