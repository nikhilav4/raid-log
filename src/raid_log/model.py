"""Pydantic model of the shared RAID register format."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

ID_PATTERN = r"^[RAID]-\d{3,}$"


class ItemType(StrEnum):
    RISK = "risk"
    ASSUMPTION = "assumption"
    ISSUE = "issue"
    DEPENDENCY = "dependency"

    @property
    def prefix(self) -> str:
        return self.value[0].upper()


class Status(StrEnum):
    OPEN = "open"
    MONITORING = "monitoring"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    CLOSED = "closed"

    @property
    def is_active(self) -> bool:
        return self not in (Status.RESOLVED, Status.CLOSED)


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return list(Severity).index(self) + 1


# Fields the format defines for one item type only.
TYPE_SPECIFIC_FIELDS: dict[str, ItemType] = {
    "probability": ItemType.RISK,
    "impact": ItemType.RISK,
    "severity": ItemType.ISSUE,
    "counterparty": ItemType.DEPENDENCY,
    "need_by": ItemType.DEPENDENCY,
    "validate_by": ItemType.ASSUMPTION,
}


def _blank_to_none(value: Any) -> Any:
    # An empty `owner:` or `mitigation: ""` means the same as leaving the key out, and the
    # rules should treat it that way.
    if isinstance(value, str) and not value.strip():
        return None
    return value


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionalText = Annotated[Text | None, BeforeValidator(_blank_to_none)]
Rating = Annotated[int, Field(ge=1, le=5)]


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: dt.date
    note: Text


class Item(BaseModel):
    # Unknown keys are kept rather than rejected so `raid validate` can warn about them; other
    # tools that write this format may add fields of their own.
    model_config = ConfigDict(extra="allow")

    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)]
    type: ItemType
    title: Text
    description: OptionalText = None
    owner: OptionalText = None
    status: Status
    raised: dt.date
    review_by: dt.date | None = None
    probability: Rating | None = None
    impact: Rating | None = None
    mitigation: OptionalText = None
    contingency: OptionalText = None
    workstream: OptionalText = None
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source: OptionalText = None
    resolution: OptionalText = None
    log: list[LogEntry] = Field(default_factory=list)
    severity: Severity | None = None
    counterparty: OptionalText = None
    need_by: dt.date | None = None
    validate_by: dt.date | None = None

    @property
    def exposure(self) -> int | None:
        if self.probability is None or self.impact is None:
            return None
        return self.probability * self.impact

    @property
    def is_active(self) -> bool:
        return self.status.is_active

    @property
    def last_logged(self) -> dt.date | None:
        return max((entry.date for entry in self.log), default=None)

    @property
    def last_activity(self) -> dt.date:
        return max([self.raised, *(entry.date for entry in self.log)])


class Register(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Both are required by the format. They are optional here so a register with a broken
    # header still loads and `raid validate` can report the problem against the right line.
    project: OptionalText = None
    updated: dt.date | None = None
    items: list[Item] = Field(default_factory=list)

    def get(self, item_id: str) -> Item | None:
        return next((item for item in self.items if item.id == item_id), None)

    @property
    def title(self) -> str:
        return self.project or "RAID register"
