from textwrap import dedent

import pytest
from typer.testing import CliRunner

from raid_log.cli import app

from .factories import make_item, register_text

runner = CliRunner()

HAND_WRITTEN = dedent("""\
    # Fictional project for the tests.
    project: EHR Integration Phase 2
    updated: 2026-10-27   # bump on every edit
    items:
      - id: R-001
        type: risk
        title: Interface vendor may slip the HL7 ADT feed
        description: >-
          Real-time admit, discharge and transfer messages drive the census.
          The vendor has moved the test feed date once already.
        owner: Priya Shah
        status: mitigating
        raised: 2026-09-02
        review_by: 2026-11-03
        probability: 4
        impact: 5
        mitigation: 'Weekly vendor checkpoint; flat-file fallback scoped'
        links: [D-001]
        log:
          - {date: 2026-10-07, note: "Vendor moved the test feed, again"}

      # Waiting on hospital IT.
      - id: D-001
        type: dependency
        title: Hospital IT stands up the ADT feed in test
        owner: Priya Shah
        status: open
        raised: 2026-09-02
        review_by: 2026-11-03
        counterparty: Hospital IT interface team
        need_by: 2026-11-15
    """)


def write(tmp_path, text):
    path = tmp_path / "raid.yaml"
    path.write_text(text)
    return path


def add(path, item_type, *options):
    args = ["add", item_type, str(path), "--title", "New item", "--owner", "Sam Patel"]
    return runner.invoke(app, [*args, *options, "--today", "2026-10-28"])


def test_appends_the_item_and_leaves_the_rest_of_the_file_alone(tmp_path):
    path = write(tmp_path, HAND_WRITTEN)

    result = add(
        path,
        "issue",
        "--severity",
        "high",
        "--workstream",
        "Data migration",
        "--link",
        "D-001",
        "--tag",
        "patient-safety",
        "--tag",
        "migration",
    )

    assert result.exit_code == 0, result.output
    assert result.output == "I-001\n"
    head = HAND_WRITTEN.replace("updated: 2026-10-27", "updated: 2026-10-28")
    text = path.read_text()
    assert text.startswith(head)
    assert text[len(head) :] == (
        "\n"
        "  - id: I-001\n"
        "    type: issue\n"
        "    title: New item\n"
        "    owner: Sam Patel\n"
        "    status: open\n"
        "    raised: 2026-10-28\n"
        "    review_by: 2026-11-11\n"
        "    severity: high\n"
        "    workstream: Data migration\n"
        "    links: [D-001]\n"
        "    tags: [patient-safety, migration]\n"
    )


@pytest.mark.parametrize(
    "options",
    [
        ["risk", "-p", "4", "-i", "5", "--mitigation", "Weekly vendor checkpoint"],
        ["assumption", "--validate-by", "2026-11-20", "--status", "monitoring"],
        ["issue", "--severity", "low", "--link", "R-001", "--source", "Steering 2026-10-27"],
        ["dependency", "--counterparty", "Privacy office", "--need-by", "2026-11-20"],
    ],
)
def test_added_item_validates_clean(tmp_path, options):
    path = write(tmp_path, register_text(make_item("R-001"), make_item("D-001")))

    added = add(path, *options)
    checked = runner.invoke(app, ["validate", str(path), "--today", "2026-10-28"])

    assert added.exit_code == 0, added.output
    assert checked.output == f"{path}: 3 items, no problems\n"


def test_starts_an_empty_register(tmp_path):
    path = write(tmp_path, "project: EHR Integration Phase 2\nitems: []\n")

    result = add(path, "risk", "-p", "2", "-i", "3", "--raised", "2026-10-27")

    assert result.output == "R-001\n"
    assert path.read_text() == dedent("""\
        project: EHR Integration Phase 2
        updated: 2026-10-28
        items:
          - id: R-001
            type: risk
            title: New item
            owner: Sam Patel
            status: open
            raised: 2026-10-27
            review_by: 2026-11-11
            probability: 2
            impact: 3
        """)


def test_missing_register_is_not_created(tmp_path):
    result = add(tmp_path / "raid.yaml", "risk", "-p", "2", "-i", "3")

    assert result.exit_code == 2
    assert "no such file" in result.output
    assert not (tmp_path / "raid.yaml").exists()
