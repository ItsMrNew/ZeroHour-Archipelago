"""Execute the actual x86 thunk in an emulator, including stack/call ABI checks."""
import struct
import ctypes as ct
from types import SimpleNamespace

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
    UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP,
    UC_X86_REG_ESP, UC_X86_REG_EFLAGS)

from zh.power import (build_stub, PowerOutage, TABLE_LAYOUTS, UPDATE_RVA,
                      BROWNOUT_RVA, ENERGY_VTABLE_RVA, PLAYER_LIST_RVA,
                      GAME_LOGIC_RVA, CAMPAIGN_GLOBAL_RVA)
from zh.gameplay import UI_RVA, UI_TABLE_RVA, INPUT_OFFSET
from zh.memory import MemoryReadError


class Simulation:
    base, code, logic, player = 0x400000, 0x2000000, 0x2200000, 0x2201000
    players, manager = 0x2202000, 0x2203000
    stack, campaign, mission = 0x220E000, 0x2204000, 0x2205000

    def __init__(self):
        self.mailbox = self.code + 0x2000
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.uc.mem_map(self.base, 0x700000)
        self.uc.mem_map(self.code, 0x3000)
        from zh import radar_outage
        self.uc.mem_map(self.code + radar_outage.PAGE, 0x1000)
        self.uc.mem_write(self.code + radar_outage.PAGE, radar_outage.page(self.base, self.code, self.mailbox))
        self.uc.mem_map(self.logic, 0x10000)
        self.uc.mem_write(self.code, build_stub(self.base, self.code, self.mailbox))
        # Stand-in at the exact native thiscall address; callback hook observes it.
        self.uc.mem_write(self.base + BROWNOUT_RVA, b'\xc2\x04\x00')
        for address, value in {
            self.base + UI_RVA: 0x220D000,
            0x220D000: self.base + UI_TABLE_RVA,
            0x220D000 + INPUT_OFFSET: 1,
            self.base + GAME_LOGIC_RVA: self.logic,
            self.base + PLAYER_LIST_RVA: self.players,
            self.base + CAMPAIGN_GLOBAL_RVA: self.manager,
            self.players + 0xC: self.player,
            self.player + 0x80: self.base + ENERGY_VTABLE_RVA,
            self.player + 0x84: 20, self.player + 0x88: 10,
            self.player + 0x90: self.player,
            self.logic + 0x3C: 300,
            self.manager + 8: self.campaign, self.manager + 12: self.mission,
            self.mailbox: 1, self.mailbox + 4: self.player,
            self.mailbox + 8: 300, self.mailbox + 12: 900,
            self.mailbox + 16: self.campaign, self.mailbox + 20: self.mission,
        }.items():
            self.put(address, value)
        self.calls = []
        self.uc.hook_add(UC_HOOK_CODE, self.observe)

    def put(self, address, value):
        self.uc.mem_write(address, struct.pack('<I', value))

    def get(self, address):
        return struct.unpack('<I', self.uc.mem_read(address, 4))[0]

    def observe(self, uc, address, size, user_data):
        if address == self.base + BROWNOUT_RVA:
            self.calls.append((uc.reg_read(UC_X86_REG_ECX),
                               self.get(uc.reg_read(UC_X86_REG_ESP) + 4)))
            # Native code may clobber caller-saved registers and flags.
            for reg in (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX):
                uc.reg_write(reg, 0xDEADBEEF)
            uc.reg_write(UC_X86_REG_EFLAGS, 0x246)

    def run(self):
        registers = {UC_X86_REG_EAX: 0x1111, UC_X86_REG_EBX: 0x2222,
            UC_X86_REG_ECX: self.logic, UC_X86_REG_EDX: 0x4444,
            UC_X86_REG_ESI: 0x5555, UC_X86_REG_EDI: 0x6666,
            UC_X86_REG_EBP: 0x7777, UC_X86_REG_ESP: self.stack,
            UC_X86_REG_EFLAGS: 0x202}
        for reg, value in registers.items():
            self.uc.reg_write(reg, value)
        self.put(self.stack, 0x12345678)
        self.uc.emu_start(self.code, self.base + UPDATE_RVA, count=getattr(self, 'instruction_budget', 500))
        for reg, expected in registers.items():
            assert self.uc.reg_read(reg) == expected
        assert self.get(self.stack) == 0x12345678


def test_thunk_calls_native_brownout_once_on_local_player_and_preserves_abi():
    game = Simulation()
    game.run()
    assert game.calls == [(game.player, 1)]
    assert game.get(game.player + 0x8C) == 1200
    assert game.get(game.mailbox) == 2
    assert game.get(game.mailbox + 24) == 1200
    assert game.get(game.player + 0x84) == 20
    assert game.get(game.player + 0x88) == 10
    game.run()
    assert len(game.calls) == 1


def test_thunk_extends_timer_and_uses_current_simulation_frame():
    game = Simulation()
    game.put(game.player + 0x8C, 1500)
    game.put(game.mailbox + 12, 1800)
    game.run()
    assert game.get(game.player + 0x8C) == 3300
    game.put(game.mailbox, 1)
    game.put(game.logic + 0x3C, 4000)
    game.run()
    assert game.get(game.player + 0x8C) == 5800


@pytest.mark.parametrize('change', ['logic', 'loading_map', 'loading_save', 'new_game',
    'mode', 'rewound', 'player_list', 'local_player', 'different_player', 'vtable',
    'owner', 'manager', 'victory', 'campaign', 'mission', 'overflow'])
def test_thunk_rejects_stale_or_unsafe_request_without_writes(change):
    game = Simulation()
    changes = {
        'logic': (game.base + GAME_LOGIC_RVA, 0),
        'loading_map': (game.logic + 0x51, 1),
        'loading_save': (game.logic + 0x52, 1),
        'new_game': (game.logic + 0x64, 1),
        'mode': (game.logic + 0x94, 1),
        'rewound': (game.logic + 0x3C, 20),
        'player_list': (game.base + PLAYER_LIST_RVA, 0),
        'local_player': (game.players + 0xC, 0),
        'different_player': (game.mailbox + 4, game.player + 4),
        'vtable': (game.player + 0x80, 0),
        'owner': (game.player + 0x90, 0),
        'manager': (game.base + CAMPAIGN_GLOBAL_RVA, 0),
        'victory': (game.manager + 16, 1),
        'campaign': (game.manager + 8, 0),
        'mission': (game.manager + 12, 0),
        'overflow': (game.mailbox + 12, 0xFFFFFFFF),
    }
    game.put(*changes[change])
    game.run()
    assert game.get(game.mailbox) == 3
    assert game.get(game.player + 0x8C) == 0
    assert not game.calls


@pytest.mark.parametrize('status', [0, 2, 3, 4])
def test_thunk_ignores_idle_completed_or_claimed_requests(status):
    game = Simulation()
    game.put(game.mailbox, status)
    game.run()
    assert game.get(game.mailbox) == status
    assert not game.calls


def test_power_poll_and_cleanup_do_not_free_published_code():
    class Game:
        base = 0x400000
        values = {0x20000: 0x50000, 0x60000: 1, 0x60A00: 0, 0xA39B00: 0}
        def pointer(self, address):
            return self.values[address]
        def replace_pointer(self, address, expected, value):
            assert self.values[address] == expected
            self.values[address] = value
    game = Game()
    power = PowerOutage(game)
    power.logic, power.table, power.region, power.mailbox = 0x20000, 0x50000, 0x40000, 0x60000
    power.original = 0x967B98
    power.reported = False
    assert power.busy and power.poll() == []
    game.values[power.mailbox] = 2
    assert not power.busy and 'brownout activated' in power.poll()[0]
    assert power.poll() == []
    power.close()
    assert game.values[power.logic] == power.original
    assert power.region == 0x40000  # deliberately retained for in-flight dispatch


def test_power_rejected_request_is_reported_once():
    game = type('Game', (), {'pointer': lambda self, address: 3})()
    power = PowerOutage(game)
    power.mailbox, power.reported = 0x20000, False
    with pytest.raises(MemoryReadError, match='rejected'):
        power.poll()
    assert power.poll() == []


class InstallGame:
    base, pid, logic, manager, player = 0x400000, 123, 0x20000, 0x21000, 0x22000
    def __init__(self, table_rva):
        self.mem, self.protections, self.allocations = {}, [], 0
        self.api = SimpleNamespace(OpenProcess=lambda *args: 1, CloseHandle=lambda *args: True,
            VirtualAllocEx=self.alloc, WriteProcessMemory=self.write,
            VirtualProtectEx=self.protect, FlushInstructionCache=lambda *args: True)
        self.original = self.base + table_rva
        self.put(self.logic, self.original)
        self.put(self.original - 4, 0xABCDEF)
        for i, rva in enumerate(TABLE_LAYOUTS[table_rva]):
            self.put(self.original + i * 4, self.base + rva)
        self.put(self.base + CAMPAIGN_GLOBAL_RVA, self.manager)
        self.put(self.manager + 8, 0x23000)
        self.put(self.manager + 12, 0x24000)
        self.store(self.manager + 16, b'\0')
        self.store(self.base + BROWNOUT_RVA, bytes.fromhex('8a 44 24 04 84 c0 56 57'))
        from zh import radar_outage
        self.store(self.base + radar_outage.NEW_MAP + 0x2A, bytes.fromhex('8d4e04898630130000'))
        self.store(self.base + 0xF9A20 + 0x16, bytes.fromhex('8986d8010000'))
        self.store(self.base + 0xF9A50 + 0x16, bytes.fromhex('8986e0010000'))
        self.put(self.base + radar_outage.RADAR, 0)
    def store(self, address, data):
        self.mem.update({address+i: value for i, value in enumerate(data)})
    def put(self, address, value):
        self.store(address, struct.pack('<I', value))
    def read(self, address, size):
        return bytes(self.mem[address+i] for i in range(size))
    def pointer(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]
    def replace_pointer(self, address, expected, value):
        assert self.pointer(address) == expected
        self.put(address, value)
    def alloc(self, handle, address, size, flags, protection):
        self.allocations += 1
        self.store(0x30000, bytes(size))
        return 0x30000
    def write(self, handle, address, data, size, written):
        self.store(address, ct.string_at(data, size))
        written._obj.value = size
        return True
    def protect(self, handle, address, size, protection, previous):
        self.protections.append((address, size, protection))
        return True


@pytest.mark.parametrize('table_rva', TABLE_LAYOUTS)
def test_install_clones_actual_class_table_and_restores_original(table_rva):
    game = InstallGame(table_rva)
    power = PowerOutage(game)
    state = SimpleNamespace(logic=game.logic, player=game.player, frame=300)
    power.prepare(state, 2)
    assert game.pointer(game.logic) == power.table
    assert game.pointer(power.table - 4) == 0xABCDEF
    for i in range(8):
        assert game.pointer(power.table+i*4) == (power.region if i == 4 else game.pointer(game.original+i*4))
    assert game.pointer(power.mailbox) == 0
    assert game.pointer(power.mailbox+12) == 1800
    assert game.protections == [(power.region, 4096, 0x20), (power.region+4096, 4096, 0x02),
                                (power.region+0x5000, 4096, 0x20)]
    power.arm()
    assert power.busy and game.pointer(power.mailbox) == 1
    power.close()
    assert game.pointer(game.logic) == game.original


def test_unknown_dispatch_table_is_rejected_without_allocation():
    game = InstallGame(0x567B98)
    game.put(game.logic, 0xDEADBEEF)
    with pytest.raises(MemoryReadError, match='already hooked'):
        PowerOutage(game).install(SimpleNamespace(logic=game.logic))
    assert game.allocations == 0


def test_failed_install_does_not_allocate_repeatedly():
    game = InstallGame(0x567B98)
    game.api.VirtualProtectEx = lambda *args: False
    power = PowerOutage(game)
    with pytest.raises(MemoryReadError, match='protect'):
        power.install(SimpleNamespace(logic=game.logic))
    with pytest.raises(MemoryReadError, match='incomplete'):
        power.install(SimpleNamespace(logic=game.logic))
    assert game.allocations == 1 and game.pointer(game.logic) == game.original


def test_power_deferred_on_game_thread_when_cutscene_starts_after_queueing():
    game = Simulation()
    game.put(0x220D000 + INPUT_OFFSET, 0)
    for frame in (300, 600, 1800):
        game.put(game.logic + 0x3C, frame)
        game.run()
        assert game.get(game.mailbox) == 1
        assert game.get(game.player + 0x8C) == 0 and not game.calls
    game.put(0x220D000 + INPUT_OFFSET, 1)
    game.run()
    assert game.get(game.player + 0x8C) == 2700  # full 30 seconds after control
    assert game.get(game.mailbox) == 2
    game.run()
    assert len(game.calls) == 1
