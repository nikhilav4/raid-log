from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Level(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    level: Level
    rule: str
    message: str
    item_id: str | None = None
    line: int | None = None

    @property
    def is_error(self) -> bool:
        return self.level is Level.ERROR


def error(rule: str, message: str, item_id: str | None = None, line: int | None = None) -> Finding:
    return Finding(Level.ERROR, rule, message, item_id, line)


def warning(
    rule: str, message: str, item_id: str | None = None, line: int | None = None
) -> Finding:
    return Finding(Level.WARNING, rule, message, item_id, line)
