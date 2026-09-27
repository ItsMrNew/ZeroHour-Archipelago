import pytest

from zh.inventory import Inventory, InventorySyncRequired


def item(code=100, location=200):
    return {"item": code, "location": location, "player": 1, "flags": 1}


def test_initial_inventory_append_and_reconnect_do_not_duplicate_grants():
    inventory = Inventory()
    inventory.apply(0, [item()])
    inventory.apply(1, [item(101)])
    inventory.apply(0, [item(), item(101)])
    assert inventory.count(100) == 1
    assert inventory.count(101) == 1


def test_authoritative_inventory_can_remove_cached_items():
    inventory = Inventory()
    inventory.apply(0, [item()])
    inventory.apply(0, [])
    assert inventory.items == ()


def test_out_of_order_and_duplicate_batches_require_sync_without_appending():
    inventory = Inventory()
    inventory.apply(0, [item()])
    with pytest.raises(InventorySyncRequired):
        inventory.apply(3, [item(101)])
    assert len(inventory.items) == 1
    assert not inventory.synchronized
    inventory.apply(0, [item()])
    inventory.apply(1, [item(101)])
    with pytest.raises(InventorySyncRequired):
        inventory.apply(1, [item(101)])
    assert len(inventory.items) == 2


def test_initial_nonzero_batch_never_grants_items():
    inventory = Inventory()
    with pytest.raises(InventorySyncRequired):
        inventory.apply(1, [item()])
    assert inventory.items == ()


@pytest.mark.parametrize(("index", "values"), [(-1, []), (True, []), (0, {}),
    (0, [None]), (0, [{"item": "100"}]), (0, [{"item": True, "location": 1, "player": 1, "flags": 0}])])
def test_invalid_packets_leave_inventory_unchanged(index, values):
    inventory = Inventory()
    with pytest.raises(ValueError):
        inventory.apply(index, values)
    assert not inventory.items

