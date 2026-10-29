"""Read a register file, keeping YAML line numbers so findings can point at the source."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails
from ruamel.yaml import YAML
from ruamel.yaml.constructor import RoundTripConstructor
from ruamel.yaml.error import YAMLError

from raid_log.findings import Finding, error
from raid_log.model import Item, Register


class RegisterError(Exception):
    """The file cannot be read as a register at all (missing, not YAML, wrong shape)."""


class _Constructor(RoundTripConstructor):
    def construct_yaml_timestamp(self, node: Any, values: Any = None) -> Any:
        try:
            return super().construct_yaml_timestamp(node, values)
        except ValueError:
            # 2026-02-30 matches YAML's date pattern but is not a real date. Keep the text so
            # the schema check reports it against its line instead of the parser crashing.
            return self.construct_scalar(node)


_Constructor.add_constructor("tag:yaml.org,2002:timestamp", _Constructor.construct_yaml_timestamp)


def yaml_round_trip() -> YAML:
    yaml = YAML()
    yaml.Constructor = _Constructor
    return yaml


@dataclass(frozen=True)
class Located:
    item: Item
    line: int | None
    key_lines: Mapping[str, int]

    def line_of(self, key: str) -> int | None:
        return self.key_lines.get(key, self.line)


@dataclass(frozen=True)
class RawEntry:
    """An item as written in the file, whether or not it passed the schema."""

    item_id: str | None
    line: int | None


@dataclass
class Loaded:
    path: Path
    register: Register
    located: list[Located]
    raw: list[RawEntry]
    findings: list[Finding] = field(default_factory=list)
    header_lines: Mapping[str, int] = field(default_factory=dict)

    @property
    def skipped(self) -> int:
        """Items left out of `register` because they failed the schema."""
        return len(self.raw) - len(self.located)


def load(path: Path) -> Loaded:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RegisterError(f"{path}: no such file") from None
    return parse(text, path)


def parse(text: str, path: Path) -> Loaded:
    try:
        data = yaml_round_trip().load(text)
    except YAMLError as exc:
        raise RegisterError(f"{path}: not valid YAML\n{exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise RegisterError(f"{path}: expected a mapping with project, updated and items")

    findings: list[Finding] = []
    header_lines = _key_lines(data)
    header = {key: value for key, value in data.items() if key != "items"}
    register = _validate_header(header, header_lines, findings)

    raw_items = data.get("items") or []
    if not isinstance(raw_items, list):
        raise RegisterError(f"{path}: `items` must be a list")

    located: list[Located] = []
    raw: list[RawEntry] = []
    for index, raw_item in enumerate(raw_items):
        line = _entry_line(raw_items, index)
        if not isinstance(raw_item, Mapping):
            raw.append(RawEntry(None, line))
            findings.append(error("schema", "each item must be a mapping of fields", line=line))
            continue
        item_id = None if raw_item.get("id") is None else str(raw_item["id"])
        raw.append(RawEntry(item_id, line))
        key_lines = _key_lines(raw_item)
        try:
            item = Item.model_validate(dict(raw_item))
        except ValidationError as exc:
            findings.extend(_schema_findings(exc, item_id, key_lines, line))
            continue
        located.append(Located(item, line, key_lines))

    register.items = [entry.item for entry in located]
    return Loaded(path, register, located, raw, findings, header_lines)


def _validate_header(
    header: dict[str, Any], lines: Mapping[str, int], findings: list[Finding]
) -> Register:
    bad: set[str] = set()
    try:
        register = Register.model_validate(header)
    except ValidationError as exc:
        findings.extend(_schema_findings(exc, None, lines, None))
        bad = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
        register = Register.model_validate({k: v for k, v in header.items() if k not in bad})
    for key in ("project", "updated"):
        if getattr(register, key) is None and key not in bad:
            findings.append(error("schema", f"missing required field `{key}`", line=lines.get(key)))
    return register


def _entry_line(seq: Any, index: int) -> int | None:
    lc = getattr(seq, "lc", None)
    return None if lc is None else lc.item(index)[0] + 1


def _key_lines(node: Any) -> dict[str, int]:
    lc = getattr(node, "lc", None)
    if lc is None:
        return {}
    return {str(key): lc.key(key)[0] + 1 for key in node}


def _schema_findings(
    exc: ValidationError, item_id: str | None, key_lines: Mapping[str, int], line: int | None
) -> list[Finding]:
    findings = []
    for err in exc.errors():
        loc = err["loc"]
        where = key_lines.get(str(loc[0]), line) if loc else line
        findings.append(error("schema", _describe(err), item_id=item_id, line=where))
    return findings


def _describe(err: ErrorDetails) -> str:
    field_path = _path(err["loc"])
    kind = err["type"]
    value = err.get("input")
    if kind == "missing":
        return f"missing required field `{field_path}`"
    if kind == "enum":
        return f"{field_path}: {value!r} is not one of {err.get('ctx', {}).get('expected')}"
    if kind.startswith("date"):
        return f"{field_path}: {value!r} is not a date (use YYYY-MM-DD)"
    if kind == "string_pattern_mismatch" and field_path == "id":
        return (
            f"id {value!r} should look like R-001: R, A, I or D, a hyphen, "
            "then three or more digits"
        )
    if kind.startswith("int") or kind in ("greater_than_equal", "less_than_equal"):
        return f"{field_path} must be a whole number from 1 to 5 (got {value!r})"
    if kind == "string_too_short":
        return f"{field_path} must not be empty"
    if kind == "string_type":
        return f"{field_path} must be text (got {value!r})"
    if kind == "list_type":
        return f"{field_path} must be a list, for example [D-003]"
    if kind == "extra_forbidden":
        return f"unexpected field `{field_path}`"
    return f"{field_path}: {err['msg']}"


def _path(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out
