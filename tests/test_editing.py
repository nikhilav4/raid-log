from raid_log.editing import next_id
from raid_log.model import ItemType

from .factories import load_items, make_item


def test_empty_register_starts_at_001():
    assert next_id([], ItemType.RISK) == "R-001"


def test_gaps_are_not_reused():
    assert next_id(["R-001", "R-004", "R-002"], ItemType.RISK) == "R-005"


def test_width_of_existing_ids_is_kept():
    assert next_id(["R-002", "R-1000"], ItemType.RISK) == "R-1001"
    assert next_id(["R-0041", "R-0042"], ItemType.RISK) == "R-0043"
    assert next_id(["R-999"], ItemType.RISK) == "R-1000"


def test_prefixes_are_independent():
    ids = ["R-001", "R-002", "I-007", "D-003"]

    assert next_id(ids, ItemType.ISSUE) == "I-008"
    assert next_id(ids, ItemType.DEPENDENCY) == "D-004"
    assert next_id(ids, ItemType.ASSUMPTION) == "A-001"


def test_items_that_fail_the_schema_keep_their_id():
    loaded = load_items(make_item("R-001"), make_item("R-002", status="blocked"))

    assert loaded.skipped == 1
    assert next_id((entry.item_id for entry in loaded.raw), ItemType.RISK) == "R-003"
