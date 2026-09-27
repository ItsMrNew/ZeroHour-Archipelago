import asyncio

import pytest

from test_client import Socket
from test_effects import inventory
from test_mission_sets import packet
from zh.client import ZeroHourClient, IncompatibleRoom
from zh.mission_data import (BASE_ID, ALL_MISSIONS, ALL_CHECKS, SET_BONUSES,
    BUILDER_ITEMS, CONSUMABLE_CONFIG, PATRIOT_ABILITY_CONFIG, GENERALS_CONFIG,
    MISSION_SETS, with_set_bonuses, earned_set_bonuses, select_missions)


def configurable_packet(mission_checks=1, set_checks=5, exclude=False):
    result = packet(exclude=exclude)
    data = result['slot_data']
    ids = sorted(m['id'] for m in with_set_bonuses(select_missions(disable_unit_only=exclude), mission_checks, set_checks))
    data.update(protocol_version=15, mission_completion_checks=mission_checks,
        set_completion_checks=set_checks, location_ids=ids, builder_menu=True,
        general_builder_unlocks=False, unit_unlocks=list(BUILDER_ITEMS.values()),
        builder_scope='campaign_and_challenge_command_centers', consumables=CONSUMABLE_CONFIG,
        abilities=PATRIOT_ABILITY_CONFIG, ability_unlocks=[], sell_random_building=True,
        sell_building_refund='normal_refund', progressive_generals_powers=False,
        generals_point_items=18, generals_points=GENERALS_CONFIG)
    result.update(missing_locations=ids)
    return result


@pytest.mark.parametrize('mission_checks', range(1,11))
@pytest.mark.parametrize('set_checks', range(11))
def test_counts_for_all_campaigns_and_challenges(mission_checks, set_checks):
    checks = with_set_bonuses(ALL_MISSIONS, mission_checks, set_checks)
    assert len(checks) == 80*mission_checks + 12*set_checks
    assert len({c['id'] for c in checks}) == len(checks)
    completed = {m['id'] for m in ALL_MISSIONS}
    assert len(earned_set_bonuses(ALL_MISSIONS, completed, set_checks)) == 12*set_checks


def test_legacy_location_ids_and_names_are_preserved():
    assert len({c['name'] for c in ALL_CHECKS}) == len(ALL_CHECKS) == 920
    for index, (key, mission_set) in enumerate(MISSION_SETS.items()):
        bonuses = [b for b in SET_BONUSES if b['campaign'] == key]
        for n, b in enumerate(bonuses[:5], 1):
            assert b['id'] == BASE_ID + 0x500 + index*8 + n
            assert b['name'] == f"{mission_set['label']} - Mission Set Complete - Bonus {n}"
    assert len(with_set_bonuses(select_missions())) == 30


@pytest.mark.parametrize('mission_checks,set_checks', [(1,5),(1,0),(10,0),(10,10),(3,7)])
@pytest.mark.parametrize('exclude', [False,True])
def test_victory_replay_reconnect_and_set_completion(tmp_path, mission_checks, set_checks, exclude):
    async def run():
        sock = Socket()
        c = ZeroHourClient('localhost:1','test',state_dir=tmp_path)
        await c.handle(sock,dict(cmd='RoomInfo',seed_name='counts'))
        config = configurable_packet(mission_checks, set_checks, exclude)
        await c.handle(sock, config)
        usa = [m['id'] for m in c.selected_missions if m['campaign']=='usa']
        c.victory(usa[0]); assert not c.progress.completed  # locked mission still rejected
        c.inventory = inventory(MISSION_SETS['usa']['item_id']); c.inventory_confirmed=True
        for i, location in enumerate(usa):
            c.victory(location)
            expected = (i+1)*mission_checks + (set_checks if i==len(usa)-1 else 0)
            assert len(c.progress.completed) == expected
            c.victory(location); assert len(c.progress.completed) == expected
        restored = ZeroHourClient('localhost:1','test',state_dir=tmp_path)
        await restored.handle(sock,dict(cmd='RoomInfo',seed_name='counts'))
        await restored.handle(sock,config)
        assert restored.progress.completed == c.progress.completed
    asyncio.run(run())


@pytest.mark.parametrize('key,value', [('mission_completion_checks',0),('mission_completion_checks',11),
    ('mission_completion_checks',True),('mission_completion_checks','2'),
    ('set_completion_checks',-1),('set_completion_checks',11),('set_completion_checks',False)])
def test_client_rejects_invalid_counts(tmp_path,key,value):
    async def run():
        c = ZeroHourClient('localhost:1','test',state_dir=tmp_path)
        data = configurable_packet(); data['slot_data'][key] = value
        with pytest.raises(IncompatibleRoom,match='check counts'):
            await c.handle(Socket(),data)
    asyncio.run(run())


def test_server_acknowledgement_recovers_extra_checks_and_changed_counts_are_rejected(tmp_path):
    async def run():
        c=ZeroHourClient('localhost:1','test',state_dir=tmp_path); sock=Socket()
        await c.handle(sock,dict(cmd='RoomInfo',seed_name='partial'))
        data=configurable_packet(10,0)
        await c.handle(sock,data)
        canonical=next(m['id'] for m in ALL_MISSIONS if m['key']=='usa_01')
        await c.handle(sock,dict(cmd='RoomUpdate',checked_locations=[canonical]))
        assert len(c.progress.completed)==10
        await c.handle(sock,dict(cmd='RoomUpdate',checked_locations=[canonical]))
        assert len(c.progress.completed)==10
        with pytest.raises(IncompatibleRoom,match='counts changed'):
            await c.handle(sock,configurable_packet(9,0))
    asyncio.run(run())
