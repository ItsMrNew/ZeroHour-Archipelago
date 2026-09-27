import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP

from zh.deathlink import (MissionState, FailureDetector, MissionRestart,
    build_restart_stub, CLIENT_TABLE_RVA, CLIENT_TABLE, CLIENT_UPDATE_RVA,
    GAME_CLIENT_RVA, RESTART_RVA, SCRIPT_ENGINE_RVA, SCRIPT_VTABLE_RVA,
    END_TIMER_OFFSET, mission_state)
from zh.mission_data import LOCATION_IDS, EFFECT_CONFIG, BUILDER_ITEMS
from zh.detector import Snapshot
from zh.client import ZeroHourClient, IncompatibleRoom
from zh.memory import MemoryReadError
from test_client import Socket, connected
from test_power import Simulation, InstallGame


def state(**changes):
    return replace(MissionState(0x20000, 300, 0x30000, 0x40000,
                               min(LOCATION_IDS), False), **changes)


def test_failure_requires_active_observation_and_sends_once():
    d = FailureDetector()
    assert d.observe(state(failed=True)) is None  # connected on defeat screen
    assert d.observe(state()) is None
    assert d.observe(state(failed=True)) == min(LOCATION_IDS)
    assert d.observe(state(failed=True)) is None
    d.observe(None)
    d.observe(state(frame=60))
    assert d.observe(state(frame=100, failed=True)) == min(LOCATION_IDS)


def test_remote_restart_suppresses_echo_but_next_mission_can_fail():
    d = FailureDetector()
    d.observe(state())
    d.suppress(state())
    assert d.observe(state(frame=301, failed=True)) is None
    d.observe(state(frame=60))  # fresh restart: frame rewound
    assert d.observe(state(frame=100, failed=True)) == min(LOCATION_IDS)


class RestartSimulation(Simulation):
    client, scripts = 0x2206000, 0x2300000
    def __init__(self):
        super().__init__()
        self.uc.mem_map(self.scripts, 0x20000)
        self.uc.mem_write(self.code, build_restart_stub(self.base, self.code, self.mailbox))
        self.uc.mem_write(self.base + RESTART_RVA, b'\xc3')
        self.put(self.base + GAME_CLIENT_RVA, self.client)
        self.put(self.base + SCRIPT_ENGINE_RVA, self.scripts)
        self.put(self.scripts, self.base + SCRIPT_VTABLE_RVA)
        self.put(self.scripts + END_TIMER_OFFSET, 0xFFFFFFFF)
        self.put(self.mailbox + 4, self.logic)
        self.uc.reg_write(UC_X86_REG_ECX, self.client)
    def observe(self, uc, address, size, user_data):
        if address == self.base + RESTART_RVA:
            self.calls.append(address)
    def run(self):
        # The normal simulation test checks full registers for power; this checks
        # GUI this-pointer and the distinct no-argument restart callback ABI.
        self.uc.reg_write(UC_X86_REG_ECX, self.client)
        self.uc.reg_write(UC_X86_REG_ESP, self.stack)
        self.put(self.stack, 0x12345678)
        self.uc.emu_start(self.code, self.base + CLIENT_UPDATE_RVA, count=500)
        assert self.uc.reg_read(UC_X86_REG_ECX) == self.client
        assert self.uc.reg_read(UC_X86_REG_ESP) == self.stack
        assert self.get(self.stack) == 0x12345678


def test_native_restart_thunk_runs_once_and_preserves_gui_stack():
    game = RestartSimulation()
    game.run(); game.run()
    assert game.calls == [game.base + RESTART_RVA]
    assert game.get(game.mailbox) == 2


@pytest.mark.parametrize('change', ['loading', 'victory', 'defeat', 'mission', 'rewound', 'mode', 'client'])
def test_restart_thunk_rejects_changed_or_ended_mission(change):
    game = RestartSimulation()
    addresses = {'loading': (game.logic + 0x51, 1), 'victory': (game.manager + 16, 1),
        'defeat': (game.scripts + END_TIMER_OFFSET, 120), 'mission': (game.manager + 12, 0),
        'rewound': (game.logic + 0x3C, 0), 'mode': (game.logic + 0x94, 1),
        'client': (game.base + GAME_CLIENT_RVA, 0)}
    game.put(*addresses[change]); game.run()
    assert not game.calls and game.get(game.mailbox) == 3


def test_restart_install_preserves_all_43_client_methods():
    game = InstallGame(0x567B98)
    game.original = game.base + CLIENT_TABLE_RVA
    game.put(game.logic, game.original)
    game.put(game.original - 4, 0)
    for index, rva in enumerate(CLIENT_TABLE):
        game.put(game.original + index*4, game.base + rva)
    game.store(game.base + RESTART_RVA, bytes.fromhex('64 a1 00 00 00 00'))
    hook = MissionRestart(game)
    hook.install(SimpleNamespace(logic=game.logic))
    for i in range(43):
        assert game.pointer(hook.table+i*4) == (hook.region if i == 4 else game.base+CLIENT_TABLE[i])
    hook.close()
    assert game.pointer(game.logic) == game.original


def death_packet(enabled=True):
    packet = connected()
    packet['slot_data'].update(protocol_version=6, goal='all_selected_missions',
        unit_unlocks=list(BUILDER_ITEMS.values()), builder_scope='all_stock_campaign_command_centers',
        enabled_campaigns=['USA','GLA','China'], disable_unit_only_missions=False,
        selected_challenges=[], effects=EFFECT_CONFIG, death_link=enabled)
    return packet


def test_deathlink_tags_receive_duplicate_echo_and_menu_guards(tmp_path):
    async def run():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {'cmd':'RoomInfo','seed_name':'deathlink'})
        await client.handle(socket, death_packet())
        assert socket.packets[-1] == {'cmd':'ConnectUpdate','tags':['AP','DeathLink']}
        bounced = {'cmd':'Bounced','tags':['DeathLink'], 'data':{'time':1.0,'source':'other'}}
        await client.handle(socket, bounced)
        assert client.death_received is None  # main menu
        client.death_active, client.death_active_at = state(), time.monotonic()
        await client.handle(socket, bounced)
        assert client.death_received is None  # duplicate menu event must not kill next mission
        bounced['data']['time']=2.0
        await client.handle(socket, bounced)
        assert client.death_received == state()
        client.death_received = None
        await client.handle(socket, bounced)
        assert client.death_received is None
        bounced['data'].update(time=3.0,source='test')
        await client.handle(socket, bounced)
        assert client.death_received is None
        await client.handle(socket, death_packet(False))
        assert socket.packets[-1]['tags'] == ['AP']
        assert not client.death_link
    asyncio.run(run())


def test_invalid_deathlink_option_rejected(tmp_path):
    async def run():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        await client.handle(Socket(), {'cmd':'RoomInfo','seed_name':'test'})
        with pytest.raises(IncompatibleRoom, match='DeathLink'):
            await client.handle(Socket(), death_packet('true'))
    asyncio.run(run())


def test_mission_end_reader_distinguishes_failure_victory_and_loading():
    game = InstallGame(0x567B98)
    from zh.deathlink import GAME_LOGIC_RVA, CAMPAIGN_GLOBAL_RVA
    scripts = 0x70000
    game.put(game.base+GAME_LOGIC_RVA, game.logic)
    game.put(game.logic+0x94, 0); game.put(game.logic+0x3C, 300)
    game.store(game.logic+0x51, b'\0\0'); game.store(game.logic+0x64, b'\0')
    game.put(game.base+SCRIPT_ENGINE_RVA, scripts)
    game.put(scripts, game.base+SCRIPT_VTABLE_RVA)
    game.put(scripts+END_TIMER_OFFSET, 0xFFFFFFFF)
    game.snapshot = lambda: Snapshot('usa','mission01','maps/md_usa01/md_usa01.map',False)
    assert not mission_state(game).failed
    game.put(scripts+END_TIMER_OFFSET,120)
    assert mission_state(game).failed
    game.snapshot = lambda: Snapshot('usa','mission01','maps/md_usa01/md_usa01.map',True)
    assert mission_state(game) is None
    game.store(game.logic+0x51,b'\1\0')
    assert mission_state(game) is None
