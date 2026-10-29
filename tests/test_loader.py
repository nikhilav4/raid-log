from pathlib import Path
from textwrap import dedent

import pytest

from raid_log.loader import RegisterError, load, parse


def test_valid_items_load_with_line_numbers():
    text = dedent("""\
        project: EHR Integration Phase 2
        updated: 2026-10-27
        items:
          - id: R-001
            type: risk
            title: Interface vendor may slip the HL7 ADT feed
            owner: Priya Shah
            status: open
            raised: 2026-09-02
            review_by: 2026-11-01
            probability: 4
            impact: 5
            mitigation: Weekly vendor checkpoint
          - id: D-003
            type: dependency
            title: ADT feed in test
            owner: Priya Shah
            status: open
            raised: 2026-09-02
            review_by: 2026-11-01
            counterparty: Hospital IT interface team
            need_by: 2026-11-15
        """)
    loaded = parse(text, Path("raid.yaml"))

    assert loaded.findings == []
    assert [entry.item.id for entry in loaded.located] == ["R-001", "D-003"]
    assert loaded.located[0].line == 4
    assert loaded.located[0].line_of("probability") == 11
    assert loaded.located[1].line == 14
    assert loaded.register.get("R-001").exposure == 20


def test_schema_errors_name_the_item_and_line():
    text = dedent("""\
        project: Demo
        updated: 2026-10-27
        items:
          - id: R-001
            type: risk
            title: Something
            owner: Priya Shah
            status: in progress
            raised: 2026-09-02
            probability: 7
        """)
    loaded = parse(text, Path("raid.yaml"))

    messages = {(f.item_id, f.line, f.message) for f in loaded.findings}
    assert (
        "R-001",
        8,
        "status: 'in progress' is not one of 'open', 'monitoring', 'mitigating', "
        "'resolved' or 'closed'",
    ) in messages
    assert ("R-001", 10, "probability must be a whole number from 1 to 5 (got 7)") in messages
    assert loaded.located == []
    assert loaded.skipped == 1


def test_impossible_date_is_a_finding_not_a_crash():
    text = dedent("""\
        project: Demo
        updated: 2026-10-27
        items:
          - id: I-001
            type: issue
            title: Something
            owner: Sam Patel
            status: open
            raised: 2026-02-30
        """)
    loaded = parse(text, Path("raid.yaml"))

    assert [(f.line, f.message) for f in loaded.findings] == [
        (9, "raised: '2026-02-30' is not a date (use YYYY-MM-DD)")
    ]


def test_bad_id_format_is_explained():
    text = "project: Demo\nupdated: 2026-10-27\nitems:\n  - {id: R-1, type: risk}\n"
    loaded = parse(text, Path("raid.yaml"))

    assert any("should look like R-001" in f.message for f in loaded.findings)


def test_header_fields_are_required_and_not_blank():
    loaded = parse('project: ""\nitems: []\n', Path("raid.yaml"))

    assert [(f.line, f.message) for f in loaded.findings] == [
        (1, "missing required field `project`"),
        (None, "missing required field `updated`"),
    ]


def test_invalid_header_value_is_reported_once():
    loaded = parse("project: Demo\nupdated: next week\nitems: []\n", Path("raid.yaml"))

    assert [f.message for f in loaded.findings] == [
        "updated: 'next week' is not a date (use YYYY-MM-DD)"
    ]


def test_item_that_is_not_a_mapping():
    loaded = parse("project: Demo\nupdated: 2026-10-27\nitems:\n  - just text\n", Path("x.yaml"))

    assert [(f.line, f.message) for f in loaded.findings] == [
        (4, "each item must be a mapping of fields")
    ]


def test_empty_register_is_fine():
    loaded = parse("project: Demo\nupdated: 2026-10-27\nitems: []\n", Path("raid.yaml"))

    assert loaded.findings == []
    assert loaded.register.items == []


def test_unreadable_files_raise_register_error(tmp_path):
    with pytest.raises(RegisterError, match="no such file"):
        load(tmp_path / "missing.yaml")
    with pytest.raises(RegisterError, match="not valid YAML"):
        parse("items: [unclosed\n", Path("raid.yaml"))
    with pytest.raises(RegisterError, match="expected a mapping"):
        parse("- a\n- b\n", Path("raid.yaml"))
    with pytest.raises(RegisterError, match="duplicate key"):
        parse("project: Demo\nproject: Other\nupdated: 2026-10-27\n", Path("raid.yaml"))
    with pytest.raises(RegisterError, match="must be a list"):
        parse("project: Demo\nupdated: 2026-10-27\nitems: R-001\n", Path("raid.yaml"))
