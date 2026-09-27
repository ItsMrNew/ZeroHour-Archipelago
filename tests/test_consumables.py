import asyncio

import pytest

from test_effects import setup, load
from test_client import Socket
from test_mission_sets import packet
from zh.client import ZeroHourClient, IncompatibleRoom
from zh.effects import PlayerEffects
from zh.mission_data import (SUPPLY_DROP_ID, CASH_THEFT_ID, CASH_ITEM_ID,
                            CONSUMABLE_CONFIG, CONSUMABLE_ITEMS, ITEM_NAMES)


def test_supply_drop_is_once_and_does_not_increase_starting_cash(tmp_path):
    game, progress, inv, effects = setup(tmp_path, SUPPLY_DROP_ID)
    effects.expanded = True
    assert 'Supply Drop' in effects.apply(inv)[0]
    assert game.pointer(game.player + 0x38) == 25000
    effects.apply(inv)
    PlayerEffects(game, progress, expanded=True).apply(inv)
    assert game.pointer(game.player + 0x38) == 25000
    load(game, effects, inv)
    assert game.pointer(game.player + 0x38) == 20000


@pytest.mark.parametrize('balance', [0, 1, 3, 4, 19999, 20000, 1_000_000, 0xFFFFFFFF])
def test_theft_has_no_cap_and_rounds_loss_down(tmp_path, balance):
    game, progress, inv, effects = setup(tmp_path, CASH_THEFT_ID)
    effects.expanded = True
    game.values[game.player + 0x38] = balance
    effects.apply(inv)
    assert game.pointer(game.player + 0x38) == balance - balance // 4
    assert progress.effect_receipts == {0}
    effects.apply(inv)
    assert game.pointer(game.player + 0x38) == balance - balance // 4


def test_consumable_cash_order_and_multiple_thefts(tmp_path):
    game, progress, inv, effects = setup(tmp_path, SUPPLY_DROP_ID, CASH_THEFT_ID, CASH_THEFT_ID, SUPPLY_DROP_ID)
    effects.expanded = True
    effects.apply(inv)
    assert game.pointer(game.player + 0x38) == 19063  # 25k -> 18750 -> 14063 -> 19063
    assert progress.effect_receipts == {0, 1, 2, 3}


def test_cash_consumables_wait_for_control_and_never_change_future_bonus(tmp_path):
    game, progress, inv, effects = setup(tmp_path, CASH_ITEM_ID, SUPPLY_DROP_ID, CASH_THEFT_ID)
    effects.expanded = True
    game.input = b'\0'
    effects.apply(inv)
    assert not progress.effect_receipts
    game.input = b'\1'
    effects.apply(inv)
    assert not progress.effect_receipts
    game.values[game.logic + 0x3C] += 30
    effects.apply(inv)
    assert game.pointer(game.player + 0x38) == 22500
    load(game, effects, inv)
    assert game.pointer(game.player + 0x38) == 25000


def test_new_protocol_negotiates_consumables_and_retains_set_guards(tmp_path):
    async def run():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        sock = Socket()
        await client.handle(sock, {'cmd':'RoomInfo', 'seed_name':'consumables'})
        data = packet()
        data['slot_data'].update(protocol_version=9, consumables=CONSUMABLE_CONFIG)
        await client.handle(sock, data)
        assert client.consumables_mode and client.effects_mode and client.sets_mode
        data['slot_data']['consumables'] = {**CONSUMABLE_CONFIG, 'cash_theft_percent':10}
        with pytest.raises(IncompatibleRoom):
            await client.handle(sock, data)
    asyncio.run(run())


def test_item_names_and_ids_are_unique():
    assert len(CONSUMABLE_ITEMS) == 5
    assert set(CONSUMABLE_ITEMS.values()) == {'Reinforcements', 'Supply Drop', 'Cash Theft', 'Production Shutdown', 'Sell Random Building'}
    assert len(set(ITEM_NAMES.values())) == len(ITEM_NAMES)


@pytest.mark.parametrize('item_name', ['Reinforcements', 'Production Shutdown', 'Sell Random Building'])
def test_native_items_are_not_reserved_during_cutscene(tmp_path, monkeypatch, item_name):
    item_id = next(i for i, name in CONSUMABLE_ITEMS.items() if name == item_name)
    game, progress, inv, effects = setup(tmp_path, item_id)
    effects.expanded = True
    calls = []
    class Native:
        busy = False
        def __init__(self, game): pass
        def poll(self): return []
        def prepare(self, state, count, operation): calls.append(operation)
        def prepare_sale_refund(self, mode): assert mode == effects.sell_refund
        def arm(self): calls.append('armed')
    monkeypatch.setattr('zh.effects.CombatEffects', Native)
    game.input = b'\0'
    effects.apply(inv)
    assert not progress.effect_receipts and not calls
    game.input = b'\1'
    effects.apply(inv)
    assert progress.effect_receipts == {0}
    assert calls == [{'Reinforcements': 1, 'Production Shutdown': 2, 'Sell Random Building': 5}[item_name], 'armed']
    effects.apply(inv)
    assert len(calls) == 2


@pytest.mark.parametrize('protocol', [11, 12, 13])
def test_new_protocol_and_previous_ability_rooms_remain_compatible(tmp_path, protocol):
    from zh.mission_data import ALL_BUILDER_ITEMS, ABILITY_ITEMS, PATRIOT_ABILITY_CONFIG, LEGACY_ABILITY_CONFIG, PATRIOT_AIRDROP_ID, EMERGENCY_REPAIR_ID
    async def run():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        sock = Socket()
        await client.handle(sock, {'cmd':'RoomInfo', 'seed_name':'trap-update'})
        data = packet()
        data['slot_data'].update(protocol_version=protocol, consumables=CONSUMABLE_CONFIG,
            builder_menu=True, general_builder_unlocks=True,
            builder_scope='campaign_and_challenge_command_centers',
            unit_unlocks=list(ALL_BUILDER_ITEMS.values()), ability_unlocks=[name for item, name in ABILITY_ITEMS.items() if item != EMERGENCY_REPAIR_ID and (protocol == 13 or item != PATRIOT_AIRDROP_ID)],
            abilities=PATRIOT_ABILITY_CONFIG if protocol == 13 else LEGACY_ABILITY_CONFIG, sell_random_building=True,
            sell_building_refund='no_refund')
        await client.handle(sock, data)
        assert client.menu_mode and client.consumables_mode and client.ability_items == {item for item in ABILITY_ITEMS if item != EMERGENCY_REPAIR_ID and (protocol == 13 or item != PATRIOT_AIRDROP_ID)}
        assert client.sell_refund == ('no_refund' if protocol == 13 else 'normal_refund')
        if protocol in (12, 13):
            del data['slot_data']['sell_random_building']
            with pytest.raises(IncompatibleRoom, match='Sell Random Building'):
                await client.handle(sock, data)
    asyncio.run(run())
