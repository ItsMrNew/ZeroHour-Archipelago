import json

import pytest

from zh.mission_data import LOCATION_IDS
from zh.state import Progress
from zh.inventory import ReceivedItem


def test_durable_deduplicated_outbox_and_seed_isolation(tmp_path):
    first = min(LOCATION_IDS)
    state = Progress(tmp_path, "seed1", 0, 1)
    state.mark(first)
    state.mark(first)
    assert Progress(tmp_path, "seed1", 0, 1).completed == {first}
    assert Progress(tmp_path, "seed2", 0, 1).completed == set()
    assert Progress(tmp_path, "seed1", 0, 2).completed == set()
    assert Progress(tmp_path, "seed1", 1, 1).completed == set()


def test_corrupt_progress_is_not_silently_replaced(tmp_path):
    state = Progress(tmp_path, "seed", 0, 1)
    state.mark(min(LOCATION_IDS))
    state.path.write_text('{"broken": true}')
    with pytest.raises(ValueError):
        Progress(tmp_path, "seed", 0, 1)
    assert state.path.read_text() == '{"broken": true}'


def test_unknown_location_rejected(tmp_path):
    with pytest.raises(ValueError):
        Progress(tmp_path, "seed", 0, 1).mark(123)


def test_receipts_persist_without_losing_checks(tmp_path):
    first, second = sorted(LOCATION_IDS)[:2]
    state = Progress(tmp_path, "seed", 0, 1)
    state.mark(first)
    state.record_inventory((ReceivedItem(100, -2, 0, 1),))
    state.mark(second)
    restored = Progress(tmp_path, "seed", 0, 1)
    assert restored.completed == {first, second}
    assert restored.received == (ReceivedItem(100, -2, 0, 1),)
    assert Progress(tmp_path, "other-seed", 0, 1).received == ()


def test_existing_check_only_save_loads_without_migration(tmp_path):
    state = Progress(tmp_path, "seed", 0, 1)
    state.mark(min(LOCATION_IDS))
    data = json.loads(state.path.read_text())
    del data["received"]
    state.path.write_text(json.dumps(data))
    restored = Progress(tmp_path, "seed", 0, 1)
    assert restored.received == ()
    assert restored.completed == state.completed
