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


def github_annotation(path: str, finding: Finding) -> str:
    """A GitHub Actions workflow command, which shows up as an annotation on the PR diff."""
    props = [f"file={_escape_property(path)}"]
    if finding.line is not None:
        props.append(f"line={finding.line}")
    props.append(f"title={_escape_property('raid ' + finding.rule)}")
    prefix = f"{finding.item_id}: " if finding.item_id else ""
    return f"::{finding.level} {','.join(props)}::{_escape_data(prefix + finding.message)}"


def as_dict(path: str, finding: Finding) -> dict[str, object]:
    return {
        "file": path,
        "line": finding.line,
        "level": str(finding.level),
        "rule": finding.rule,
        "item": finding.item_id,
        "message": finding.message,
    }


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")
