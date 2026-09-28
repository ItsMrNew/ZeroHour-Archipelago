"""Protocol compatibility and installed stock repair recipe checks."""
import asyncio
import os
import re
from pathlib import Path

import pytest

from test_check_counts import configurable_packet
from test_consumables import Socket
from zh.client import ZeroHourClient, IncompatibleRoom
from zh.game_options import DEFAULTS
from zh.mission_data import ABILITY_CONFIG, PATRIOT_ABILITY_CONFIG, EMERGENCY_REPAIR_ID


@pytest.mark.parametrize('protocol', [15, 16, 17])
def test_repair_protocol_preserves_previous_rooms(tmp_path, protocol):
    async def run():
        c = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        sock = Socket()
        await c.handle(sock, {'cmd': 'RoomInfo', 'seed_name': 'repair'})
        packet = configurable_packet()
        data = packet['slot_data']
        data.update(protocol_version=protocol, game_options=dict(DEFAULTS),
                    abilities=ABILITY_CONFIG if protocol == 17 else PATRIOT_ABILITY_CONFIG,
                    ability_unlocks=['Emergency Repair'] if protocol == 17 else ['Patriot Airdrop'])
        await c.handle(sock, packet)
        assert (EMERGENCY_REPAIR_ID in c.ability_items) == (protocol == 17)
        data['abilities'] = {**data['abilities'], 'repair_cooldown': 1}
        with pytest.raises(IncompatibleRoom, match='ability configuration'):
            await c.handle(sock, packet)
    asyncio.run(run())


def test_installed_stock_level_three_repair_recipe():
    folder = os.environ.get('ZERO_HOUR_TEST_DIR')
    if not folder:
        pytest.skip('Set ZERO_HOUR_TEST_DIR to audit installed game assets')
    from stock_ini import read_ini, blocks, field
    marker = blocks(read_ini(folder, 'data/ini/object/system.ini'), 'Object')['RepairVehiclesInArea_InvisibleMarker_Level3']
    assert field(marker, 'HealingAmount') == '300'
    assert field(marker, 'HealingDelay') == '1'
    assert field(marker, 'Radius') == '100.0f'
    assert field(marker, 'SingleBurst') == 'Yes'
    assert field(marker, 'StartsActive') == 'Yes'
    assert re.search(r'KindOf\s*=\s*VEHICLE\s*$', marker, re.M)
    assert field(marker, 'MinLifetime') == field(marker, 'MaxLifetime') == '0'
    powers = blocks(read_ini(folder, 'data/ini/specialpower.ini'), 'SpecialPower')
    for name in ('SuperweaponEmergencyRepair', 'Early_SuperweaponEmergencyRepair'):
        assert field(powers[name], 'ReloadTime') == '240000'
