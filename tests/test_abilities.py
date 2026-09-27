import struct
from types import SimpleNamespace

import pytest
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP

from test_consumables_native import CombatSimulation
from test_unlock_menu import MenuSimulation
from zh import ability_native as a
from zh.abilities import AbilityController
from zh.mission_data import REVEAL_MINIMAP_ID, CARPET_BOMB_ID, EMERGENCY_REPAIR_ID, ABILITY_ITEMS
from zh.state import Progress


class AbilitySimulation(CombatSimulation):
    pops = {a.NEW_OBJECT: 4, a.SET_POSITION: 1, a.SET_RANGE: 1,
            a.DELETE_KEY: 0, a.FIND_MODULE: 1, a.SET_LIFETIME: 2,
            a.DESTROY: 1, a.FIND_OCL: 1, a.CREATE_OCL: 5, a.CLOSEST_EDGE: 2}

    def __init__(self, operation=3):
        super().__init__(operation)
        self.missing = None
        self.put(self.player + 0x160, self.player + 0x400)
        self.put(self.base + a.OCL_STORE_RVA, self.assistant)
        self.put(self.base + a.TERRAIN_RVA, self.anchor)
        for rva, argc in self.pops.items():
            self.uc.mem_write(self.base + rva, bytes((0xC2, argc * 4, 0)))
        self.uc.mem_write(self.mailbox + a.TARGET, struct.pack('<4fI', 1000, 1500, 0, 2000, 450))
        self.uc.mem_write(self.mailbox + a.OCL_NAME, b'AirF_SUPERWEAPON_CarpetBomb\0')

    def observe(self, uc, address, size, data):
        super().observe(uc, address, size, data)
        rva = address - self.base
        if rva not in self.pops:
            return
        sp, this = uc.reg_read(UC_X86_REG_ESP), uc.reg_read(UC_X86_REG_ECX)
        args = [self.get(sp + 4 + i * 4) for i in range(self.pops[rva])]
        self.native_calls.append((rva, this, args))
        result = 0
        if rva == a.NEW_OBJECT:
            assert args == [self.template, self.player + 0x400, 0, 0]
            result = self.anchor
        elif rva == a.DELETE_KEY:
            result = 123
        elif rva == a.FIND_MODULE:
            assert this == self.anchor and args == [123]
            result = 0 if self.missing == 'module' else self.assistant
        elif rva == a.SET_LIFETIME:
            assert this == self.assistant and args == [450, 450]
        elif rva == a.SET_POSITION:
            assert this == self.anchor and args == [self.mailbox + a.TARGET]
        elif rva == a.SET_RANGE:
            assert this == self.anchor and args == [struct.unpack('<I', struct.pack('<f', 2000))[0]]
        elif rva == a.FIND_OCL:
            assert bytes(uc.mem_read(args[0], 28)) == b'AirF_SUPERWEAPON_CarpetBomb\0'
            result = 0 if self.missing == 'ocl' else self.template
        elif rva == a.CREATE_OCL:
            assert this == self.template
            assert args == [self.anchor, self.mailbox + a.EDGE, self.mailbox + a.TARGET, 0, 0]
            result = self.anchor + 0x100 if self.missing != 'transport' else 0
        elif rva == a.CLOSEST_EDGE:
            assert args == [self.mailbox + a.EDGE, self.mailbox + a.TARGET]
        elif rva == a.DESTROY:
            assert this == self.logic and args == [self.anchor]
        uc.reg_write(UC_X86_REG_EAX, result)
        uc.reg_write(UC_X86_REG_ECX, 0xBAD)
        uc.reg_write(UC_X86_REG_EDX, 0xBAD)


@pytest.mark.parametrize('operation', [3, 4])
def test_native_abilities_use_local_team_temporary_vision_and_stock_strike(operation):
    sim = AbilitySimulation(operation)
    sim.run()
    assert sim.get(sim.mailbox) == 2
    calls = [r for r, _, _ in sim.native_calls]
    assert calls.count(a.NEW_OBJECT) == 1
    assert calls.count(a.SET_LIFETIME) == 1
    assert calls.count(a.CREATE_OCL) == (operation == 4)
    sim.run()
    assert len(calls) == len(sim.native_calls)


@pytest.mark.parametrize('failure', ['module', 'ocl', 'team', 'loading', 'player', 'mission'])
def test_native_ability_rejections_do_not_leave_permanent_vision(failure):
    sim = AbilitySimulation(4)
    sim.missing = failure
    if failure == 'team': sim.put(sim.player + 0x160, 0)
    if failure == 'loading': sim.put(sim.logic + 0x51, 1)
    if failure == 'player': sim.put(sim.players + 12, 0)
    if failure == 'mission': sim.put(sim.manager + 12, 0)
    sim.run()
    assert sim.get(sim.mailbox) == 3
    calls = [r for r, _, _ in sim.native_calls]
    assert a.SET_RANGE not in calls and a.CREATE_OCL not in calls
    assert (a.DESTROY in calls) == (failure == 'module')


def test_native_partial_strike_failure_is_not_reported_as_success_or_refundable():
    sim = AbilitySimulation(4); sim.missing = 'transport'; sim.run()
    assert sim.get(sim.mailbox) == 5


def test_repair_creates_one_local_marker_at_target_without_vision_or_lifetime_changes():
    sim = AbilitySimulation(7)
    sim.run()
    assert sim.get(sim.mailbox) == 2
    calls = [r for r, _, _ in sim.native_calls]
    assert [r for r in calls if r in sim.pops] == [a.NEW_OBJECT, a.SET_POSITION]
    sim.run()
    assert [r for r, _, _ in sim.native_calls] == calls


@pytest.mark.parametrize('failure', ['team', 'loading', 'player', 'mission'])
def test_repair_transition_guards_prevent_marker_creation(failure):
    sim = AbilitySimulation(7)
    if failure == 'team': sim.put(sim.player + 0x160, 0)
    if failure == 'loading': sim.put(sim.logic + 0x51, 1)
    if failure == 'player': sim.put(sim.players + 12, 0)
    if failure == 'mission': sim.put(sim.manager + 12, 0)
    sim.run()
    assert sim.get(sim.mailbox) == 3
    assert not sim.native_calls


class TargetSimulation(MenuSimulation):
    def __init__(self):
        super().__init__()
        self.put(self.mailbox + 120, 11)
        self.view = self.manager + 0x1E000
        self.put(self.base + 0x639598, self.view)
        self.put(self.view, self.base + 0x568B58)
        self.put(self.view + 0x18, 1024)
        self.put(self.view + 0x1C, 600)
        from zh.unlock_menu import UI_TABLE_RVA
        self.put(self.ui, self.base + UI_TABLE_RVA)
        self.cursor_calls = []
        self.cursor_shadow = self.manager + 0x1D000
        self.fail_cursor = False
        for rva in (0x637A80, 0x639B00, 0x6381BC):
            self.put(self.base + rva, self.manager + 0x1C000)
        self.put(self.base + 0x6395A0, self.manager + 0x1B000)
        self.put(self.manager + 0x1B00C, self.manager + 0x1A000)

    def hook(self, uc, address, size, data):
        from zh.unlock_menu import RADIUS_DECAL, RADIUS_SHADOW, RADIUS_TYPE, CARPET_TEMPLATE, CARPET_RADIUS_BITS
        sp = uc.reg_read(UC_X86_REG_ESP)
        this = uc.reg_read(UC_X86_REG_ECX)
        if address == self.base + 0xF9A50:
            self.ret(1)
        elif address == self.base + 0x36F100:
            screen, world = self.get(sp + 4), self.get(sp + 8)
            assert self.get(screen) == 200 and self.get(screen + 4) == 250
            uc.mem_write(world, struct.pack('<3f', 1000, 1500, 20))
            self.ret(2)
        elif address == self.base + 0x10CD00:
            assert this == self.ui and self.get(sp + 4) == 0
            self.cursor_calls.append('cancel_previous_command')
            self.put(self.ui + RADIUS_TYPE, 0)
            self.put(self.ui + RADIUS_SHADOW, 0)
            self.ret(1)
        elif address == self.base + 0x213880:
            kind = self.get(self.mailbox + 120)
            assert this == self.ui + 0x19AC + kind * 28
            args = [self.get(sp + 4 + n * 4) for n in range(4)]
            assert args == [self.mailbox + 104, struct.unpack('<I', struct.pack('<f', {13: 50.0, 11: 180.0, 5: 100.0}[kind]))[0], self.manager + 0x1A000,
                            self.ui + RADIUS_DECAL]
            self.cursor_calls.append('create')
            self.put(self.ui + RADIUS_SHADOW, 0 if self.fail_cursor else self.cursor_shadow)
            self.ret(4)
        elif address == self.base + 0x10A140:
            assert this == self.ui
            assert self.get(self.ui + RADIUS_TYPE) == self.get(self.mailbox + 120)
            self.cursor_calls.append('follow_mouse')
            self.ret()
        elif address == self.base + 0x213BB0:
            assert this == self.ui + RADIUS_DECAL
            self.cursor_calls.append('clear')
            self.put(self.ui + RADIUS_SHADOW, 0)
            self.ret()
        else:
            super().hook(uc, address, size, data)

    def target_click(self, message, x=200, y=250):
        window = self.get(self.mailbox + 64)
        self.run(self.windows[window]['input'], (window, message, x | y << 16, 0))


@pytest.mark.parametrize('button', [32, 35, 37])
def test_target_capture_cancel_hud_bounds_and_transition_cleanup(button):
    sim = TargetSimulation()
    sim.tick(); sim.click(button)
    sim.put(sim.mailbox + 120, {32: 11, 35: 13, 37: 5}[button])
    assert sim.get(sim.mailbox + 12) == button
    sim.put(sim.mailbox + 60, 1); sim.tick()
    target_window = sim.get(sim.mailbox + 64)
    assert sim.windows[target_window]['rect'] == (0, 0, 1024, 600)
    assert sim.cursor_calls == ['cancel_previous_command', 'create', 'follow_mouse']
    sim.tick()
    assert sim.cursor_calls[-1] == 'follow_mouse'
    assert sim.cursor_calls.count('create') == 1  # mouse moves do not allocate more decals
    sim.target_click(6, y=620)
    assert sim.get(sim.mailbox + 60) == 1
    sim.target_click(6)
    assert sim.get(sim.mailbox + 60) == 2
    assert sim.cursor_calls[-1] == 'clear'
    assert struct.unpack('<3f', sim.u.mem_read(sim.mailbox + 88, 12)) == (1000, 1500, 20)
    sim.tick()
    assert sim.get(target_window + 4) & 16
    sim.put(sim.mailbox + 60, 1); sim.tick(); sim.target_click(14)
    assert sim.get(sim.mailbox + 60) == 3
    assert sim.cursor_calls[-1] == 'clear'
    sim.put(sim.mailbox + 60, 1); sim.u.mem_write(sim.logic + 0x52, b'\1'); sim.tick()
    assert sim.get(sim.mailbox + 60) == 0
    assert sim.get(target_window + 4) & 16
    sim.put(sim.mailbox, 2); sim.tick()
    assert target_window in sim.destroyed


@pytest.mark.parametrize('reason', ['launcher', 'loading', 'heartbeat', 'detach', 'ui_replaced', 'foreign_cursor', 'native_command'])
@pytest.mark.parametrize('cursor', [11, 13, 5])
def test_preview_cleanup_is_owned_and_covers_every_exit(reason, cursor):
    from zh.unlock_menu import RADIUS_SHADOW, RADIUS_TYPE
    sim = TargetSimulation(); sim.put(sim.mailbox + 120, cursor)
    sim.tick(); sim.put(sim.mailbox + 60, 1); sim.tick()
    if reason == 'launcher': sim.click(1)
    elif reason == 'loading': sim.u.mem_write(sim.logic + 0x52, b'\1')
    elif reason == 'heartbeat': sim.put(sim.logic + 0x3C, 91)
    elif reason == 'detach': sim.put(sim.mailbox, 2)
    elif reason == 'ui_replaced': sim.put(sim.base + 0x639FB0, sim.manager + 0x19000)
    elif reason == 'native_command': sim.put(sim.ui + 0x143C, 0x12345)
    else:
        sim.put(sim.ui + RADIUS_SHADOW, sim.cursor_shadow + 32)
    sim.tick()
    assert sim.get(sim.mailbox + 68) == 0
    if reason in ('ui_replaced', 'foreign_cursor', 'native_command'):
        assert sim.cursor_calls.count('clear') == 0  # never dereference stale UI or delete another decal
    else:
        assert sim.cursor_calls.count('clear') == 1
        assert sim.get(sim.ui + RADIUS_TYPE) == 0


def test_preview_recreated_after_native_clear_without_selection_or_replacing_command_again():
    from zh.unlock_menu import RADIUS_SHADOW, RADIUS_TYPE
    sim = TargetSimulation(); sim.tick(); sim.put(sim.mailbox + 60, 1); sim.tick()
    sim.put(sim.ui + RADIUS_TYPE, 0); sim.put(sim.ui + RADIUS_SHADOW, 0)
    sim.tick()
    assert sim.cursor_calls.count('create') == 2
    assert sim.cursor_calls.count('cancel_previous_command') == 1
    assert sim.get(sim.mailbox + 60) == 1


def test_preview_unavailable_cancels_targeting_without_submitting_strike():
    sim = TargetSimulation(); sim.fail_cursor = True; sim.tick()
    sim.put(sim.mailbox + 60, 1); sim.tick()
    assert sim.get(sim.mailbox + 60) == 3
    assert 'follow_mouse' not in sim.cursor_calls


def controller(tmp_path, monkeypatch):
    progress = Progress(tmp_path, 'ability-test', 0, 1)
    state = SimpleNamespace(logic=1, player=2, mission=('usa', 'mission01'), frame=300,
                            loading_map=False, loading_save=False)
    effects = SimpleNamespace(progress=progress, game=object(), power=None, snapshot=lambda: state)
    monkeypatch.setattr('zh.abilities.input_enabled', lambda g: True)
    return AbilityController(effects, ABILITY_ITEMS), state


def test_cooldowns_survive_rewinds_loads_and_reconnection(tmp_path, monkeypatch):
    c, state = controller(tmp_path, monkeypatch)
    c.remaining = {'Reveal Minimap': 5400}; c.flush(); c.tick()
    state.frame += 30; c.tick()
    assert c.remaining['Reveal Minimap'] == 5370
    state.frame = 10; c.tick()
    assert c.remaining['Reveal Minimap'] == 5370
    state.loading_save = True; c.tick()
    state.loading_save = False; state.frame = 900; c.tick()
    assert c.remaining['Reveal Minimap'] == 5370
    state.frame = 9500; c.tick()  # unobserved forward load is not free cooldown
    assert c.remaining['Reveal Minimap'] == 5370
    restored = Progress(tmp_path, 'ability-test', 0, 1)
    assert restored.ability_cooldowns == c.remaining


def test_unowned_and_disabled_abilities_never_cast(tmp_path, monkeypatch):
    c, state = controller(tmp_path, monkeypatch); c.tick()
    inv = SimpleNamespace(synchronized=True, count=lambda item: 0)
    assert not c.cast(REVEAL_MINIMAP_ID, inv)
    inv.count = lambda item: 1
    c.enabled = set()
    assert not c.cast(CARPET_BOMB_ID, inv, (1000, 1000, 0))


def test_cast_reserves_before_native_publish_and_duplicate_click_cannot_recast(tmp_path, monkeypatch):
    c, state = controller(tmp_path, monkeypatch); c.tick()
    published = []
    power = SimpleNamespace(busy=False, reported=True,
        prepare_ability=lambda *args: published.append(('prepare', args)))
    def arm():
        restored = Progress(tmp_path, 'ability-test', 0, 1)
        assert restored.ability_cooldowns['Reveal Minimap'] == 5400
        published.append(('arm', None))
    power.arm = arm
    c.effects.power = power
    c.effects.check_same = lambda s: None
    monkeypatch.setattr('zh.abilities.map_bounds', lambda game: (0, 0, 0, 3000, 4000, 100))
    inv = SimpleNamespace(synchronized=True, count=lambda item: 1)
    assert c.cast(REVEAL_MINIMAP_ID, inv)
    assert published[0][1] == (state, 3, (1500, 2000, 50), 2600, 450)
    assert published[1][0] == 'arm'
    assert not c.cast(REVEAL_MINIMAP_ID, inv)
    assert len(published) == 2


def test_persistence_failure_cannot_publish_a_cast(tmp_path, monkeypatch):
    c, state = controller(tmp_path, monkeypatch); c.tick()
    power = SimpleNamespace(busy=False, reported=True, prepare_ability=lambda *args: None,
                            arm=lambda: pytest.fail('Must not publish before durable reservation'))
    c.effects.power = power; c.effects.check_same = lambda s: None
    monkeypatch.setattr('zh.abilities.map_bounds', lambda game: (0, 0, 0, 3000, 4000, 100))
    monkeypatch.setattr(c.progress, 'save_cooldowns', lambda values: (_ for _ in ()).throw(OSError('disk full')))
    inv = SimpleNamespace(synchronized=True, count=lambda item: 1)
    with pytest.raises(OSError):
        c.cast(CARPET_BOMB_ID, inv, (100, 100, 0))
    assert c.pending is None


@pytest.mark.parametrize('status, expected', [(2, 5400), (3, 0), (5, 5400)])
def test_only_explicit_native_rejection_refunds_cooldown(tmp_path, monkeypatch, status, expected):
    from zh.consumables import CombatEffects
    c, state = controller(tmp_path, monkeypatch)
    c.effects.power = CombatEffects(c.effects.game)
    c.effects.power.ability_result = (3, status)
    c.pending = REVEAL_MINIMAP_ID
    c.remaining = {'Reveal Minimap': 5400}; c.flush(); c.tick()
    assert c.remaining['Reveal Minimap'] == expected
    assert c.pending is None


class PatriotSimulation(AbilitySimulation):
    def __init__(self):
        super().__init__(6)
        self.ocl, self.nugget, self.patriot = 0x2300000, 0x2301000, 0x2302000
        self.put(self.ocl, self.ocl + 16)
        self.put(self.ocl + 4, self.ocl + 20)
        self.put(self.ocl + 16, self.nugget)
        # Steam constructor at VA 0x4BABB5: mov [esi], 0x948570.
        self.put(self.nugget, struct.unpack('<I', bytes.fromhex('70859400'))[0])
        self.put(self.nugget + 8, 0xCAFE)
        self.put(self.nugget + 0xC, 0x2303000)
        self.put(self.nugget + 0x10, 0x2303008)
        self.put(self.nugget + 0x60, 5)
        self.put(self.nugget + 0x7D, 1)
        self.put(self.patriot + 0x68, 0x80)
        self.put(self.patriot + 0x6C, 0x1020)
        self.uc.mem_write(self.mailbox + a.DROP_SPACING, struct.pack('<3f', -70, 0, 70))
        import json
        from pathlib import Path
        fixture = json.loads((Path(__file__).parent / 'fixtures/steam_airdrop_cargo.json').read_text())
        for rva, code in fixture.items():
            self.uc.mem_write(self.base + int(rva), bytes.fromhex(code))
        # The private OCL returns a plane containing three parachutes, each
        # containing a Patriot. Use actual Steam template/destination routines.
        self.cargo = 0x2310000
        self.put(self.anchor + 0x170, self.cargo)
        self.put(self.cargo, self.cargo + 0x100)
        self.put(self.cargo + 0x100 + 0xA4, self.cargo + 0x300)
        self.uc.mem_write(self.cargo + 0x300, bytes.fromhex('b803000000c3'))
        self.put(self.cargo + 0x100 + 0xA8, self.cargo + 0x320)
        self.uc.mem_write(self.cargo + 0x320, bytes.fromhex('8d4120c3'))
        self.put(self.cargo + 0x20, self.cargo + 0x30)
        self.put(self.cargo + 0x30, self.cargo + 0x400)
        self.chutes = []
        self.put(self.base + a.CHUTE_VTABLE + 0xA8, self.cargo + 0x320)
        for i in range(3):
            node, chute, contain, rider = (self.cargo + 0x400 + i * 16,
                self.cargo + 0x1000 + i * 0x1000, self.cargo + 0x1400 + i * 0x1000,
                self.cargo + 0x1800 + i * 0x1000)
            for addr, value in {node: node + 16, node + 8: chute, chute + 0x170: contain,
                contain: self.base + a.CHUTE_VTABLE, contain + 0x20: contain + 0x30,
                contain + 0x30: contain + 0x40, contain + 0x48: rider, rider + 4: self.patriot}.items():
                self.put(addr, value)
            self.chutes.append(contain)
        self.uc.mem_write(self.mailbox + a.DROP_NAME, b'AP_PatriotBattery\0')
        self.uc.mem_write(self.mailbox + a.CHUTE_NAME, b'LargeParachute\0')
        self.strings, self.released, self.drops = {}, [], []
        self.stock_before = bytes(self.uc.mem_read(self.nugget, 0xB0))

    def observe(self, uc, address, size, data):
        from zh import consumables as c
        sp, this = uc.reg_read(UC_X86_REG_ESP), uc.reg_read(UC_X86_REG_ECX)
        rva = address - self.base
        result = None
        if rva == c.ASCII_CTOR_RVA:
            ptr = self.get(sp + 4)
            self.strings[this] = bytes(uc.mem_read(ptr, 48)).split(b'\0')[0].decode()
        if rva == c.ASCII_DTOR_RVA:
            self.released.append(this)
        if rva == c.FIND_TEMPLATE_RVA and this == self.factory and self.get(sp + 4) == self.mailbox + a.DROP_STRING:
            assert self.strings[self.mailbox + a.DROP_STRING] == 'AP_PatriotBattery'
            assert self.get(sp + 8) == 0
            result = 0 if self.missing == 'patriot' else self.patriot
        elif rva == a.FIND_OCL:
            result = self.ocl
        elif rva == a.CREATE_OCL:
            assert this == self.mailbox + a.DROP_LIST
            args = [self.get(sp + 4 + i * 4) for i in range(5)]
            assert args == [self.anchor, self.mailbox + a.EDGE, self.mailbox + a.TARGET, 0, 0]
            begin, end = self.get(this), self.get(this + 4)
            assert end == begin + 4
            clone = self.get(begin)
            assert self.get(clone) == self.base + a.DELIVER_VTABLE
            payload = self.get(clone + 0xC)
            assert self.get(clone + 0x10) == payload + 8
            assert self.strings[payload] == 'AP_PatriotBattery'
            assert self.get(payload + 4) == 3
            assert self.strings[clone + 8] == 'LargeParachute'
            assert self.get(clone + 0x60) == 5
            assert uc.mem_read(clone + 0x7D, 1) == b'\0'
            assert self.get(self.patriot + 0x6C) == 0x1120
            assert uc.mem_read(self.patriot + a.TRANSPORT_SLOTS, 1) == b'\1'
            assert bytes(uc.mem_read(self.nugget, 0xB0)) == self.stock_before
            self.drops.append(args)
            result = 0 if self.missing == 'transport' else self.anchor
        if result is None:
            return super().observe(uc, address, size, data)
        uc.reg_write(UC_X86_REG_EAX, result)
        uc.reg_write(UC_X86_REG_ECX, 0xBAD)
        uc.reg_write(UC_X86_REG_EDX, 0xBAD)


@pytest.mark.parametrize('partial', [False, True])
def test_patriot_drop_uses_private_three_building_payload_and_restores_stock_data(partial):
    sim = PatriotSimulation()
    if partial: sim.missing = 'transport'
    sim.run()
    assert sim.get(sim.mailbox) == (5 if partial else 2)
    assert len(sim.drops) == 1
    assert sim.get(sim.patriot + 0x6C) == 0x1020
    assert sim.uc.mem_read(sim.patriot + a.TRANSPORT_SLOTS, 1) == b'\0'
    assert sim.get(sim.mailbox + a.DROP_COUNT) == (0 if partial else 3)
    if not partial:
        for i, chute in enumerate(sim.chutes):
            assert sim.uc.mem_read(chute + 0x688, 1) == b'\1'
            assert struct.unpack('<3f', sim.uc.mem_read(chute + 0x68C, 12)) == (930 + i * 70, 1500, 0)
    assert bytes(sim.uc.mem_read(sim.nugget, 0xB0)) == sim.stock_before
    assert sim.mailbox + a.DROP_PAYLOAD in sim.released
    assert sim.mailbox + a.DROP_CLONE + 8 in sim.released
    assert sim.nugget + 8 not in sim.released
    sim.run()
    assert len(sim.drops) == 1


@pytest.mark.parametrize('failure', ['patriot', 'layout', 'nugget', 'extra_nugget'])
def test_patriot_invalid_recipe_rejects_without_flags_or_payload_changes(failure):
    sim = PatriotSimulation()
    if failure == 'patriot': sim.missing = failure
    if failure == 'layout': sim.put(sim.patriot + 0x68, 0)
    if failure == 'nugget': sim.put(sim.nugget, 0)
    if failure == 'extra_nugget': sim.put(sim.ocl + 4, sim.ocl + 24)
    sim.run()
    assert sim.get(sim.mailbox) == 3
    assert not sim.drops
    assert sim.get(sim.patriot + 0x6C) == 0x1020


def test_patriot_drop_waits_for_control():
    from zh.gameplay import INPUT_OFFSET
    sim = PatriotSimulation()
    sim.put(0x220D000 + INPUT_OFFSET, 0)
    sim.run()
    assert sim.get(sim.mailbox) == 1 and not sim.drops
    sim.put(0x220D000 + INPUT_OFFSET, 1)
    sim.run()
    assert len(sim.drops) == 1


def test_patriot_five_minute_cooldown_is_durable_and_target_required(tmp_path, monkeypatch):
    from zh.mission_data import PATRIOT_AIRDROP_ID
    c, state = controller(tmp_path, monkeypatch); c.tick()
    c.enabled.add(PATRIOT_AIRDROP_ID)
    requests = []
    c.effects.power = SimpleNamespace(busy=False, reported=True,
        prepare_ability=lambda *args: requests.append(args), arm=lambda: None)
    c.effects.check_same = lambda s: None
    monkeypatch.setattr('zh.abilities.map_bounds', lambda g: (0, 0, 0, 3000, 4000, 100))
    inventory = SimpleNamespace(synchronized=True, count=lambda item: 1)
    assert not c.cast(PATRIOT_AIRDROP_ID, inventory)
    assert c.cast(PATRIOT_AIRDROP_ID, inventory, (500, 600, 0))
    assert requests == [(state, 6, (500, 600, 0), 250, 1200)]
    assert Progress(tmp_path, 'ability-test', 0, 1).ability_cooldowns['Patriot Airdrop'] == 9000
    assert not c.cast(PATRIOT_AIRDROP_ID, inventory, (500, 600, 0))
    c.suspend(); c.tick()
    assert c.remaining['Patriot Airdrop'] == 9000


@pytest.mark.parametrize('percent', [100, 25, 300])
def test_repair_cooldown_target_and_reservation_survive_restart(tmp_path, monkeypatch, percent):
    c, state = controller(tmp_path, monkeypatch); c.tick()
    c.effects.options = {'ability_cooldown_percent': percent}
    requests = []
    c.effects.power = SimpleNamespace(busy=False, reported=True,
        prepare_ability=lambda *args: requests.append(args), arm=lambda: None)
    c.effects.check_same = lambda s: None
    monkeypatch.setattr('zh.abilities.map_bounds', lambda g: (0, 0, 0, 3000, 4000, 100))
    inventory = SimpleNamespace(synchronized=True, count=lambda item: 1)
    assert not c.cast(EMERGENCY_REPAIR_ID, inventory)
    assert c.cast(EMERGENCY_REPAIR_ID, inventory, (500, 600, 0))
    assert requests == [(state, 7, (500, 600, 0), 100, 1200)]
    assert Progress(tmp_path, 'ability-test', 0, 1).ability_cooldowns['Emergency Repair'] == 7200 * percent // 100
    assert not c.cast(EMERGENCY_REPAIR_ID, inventory, (500, 600, 0))
    c.suspend(); c.tick()
    assert c.remaining['Emergency Repair'] == 7200 * percent // 100


@pytest.mark.parametrize('button,cancel', [(32, False), (35, False), (35, True), (37, False), (37, True)])
def test_menu_remembers_which_targeted_ability_to_cast(tmp_path, monkeypatch, button, cancel):
    from zh.unlock_menu import UnlockMenu, MANAGER_RVA
    from zh.mission_data import PATRIOT_AIRDROP_ID
    mailbox, base = 0x10000, 0x400000
    values = {base + MANAGER_RVA: 1, mailbox + 12: button, mailbox + 32: 1}
    def replace(address, old, new):
        assert values.get(address, 0) == old
        values[address] = new
    game = SimpleNamespace(base=base, pointer=lambda address: values.get(address, 0),
                           replace_pointer=replace, read=lambda address, count: struct.pack('<3f', 40, 50, 0))
    casts = []
    abilities = SimpleNamespace(tick=lambda: None, ready=lambda item, inv: True, state=True,
        cooldown=lambda item: 9000, label=lambda item, inv: ('Ready', 1), cast=lambda *args: casts.append(args), suspend=lambda: None)
    menu = UnlockMenu(game, Progress(tmp_path, 'menu-target', 0, 1), set(), abilities)
    menu.mailbox = mailbox
    menu.install = lambda state: None
    state = SimpleNamespace(failed=False, logic=10, campaign=20, mission=30, frame=1)
    monkeypatch.setattr('zh.unlock_menu.mission_state', lambda game: state)
    monkeypatch.setattr('zh.unlock_menu.input_enabled', lambda game: True)
    inventory = SimpleNamespace(synchronized=True, count=lambda item: 1)
    menu.update(inventory)
    assert values[mailbox + 60] == 1 and not casts
    assert values[mailbox + 120] == ({32: 11, 35: 13, 37: 5}[button])
    values[mailbox + 60] = 3 if cancel else 2
    menu.update(inventory)
    expected = {32: CARPET_BOMB_ID, 35: PATRIOT_AIRDROP_ID, 37: EMERGENCY_REPAIR_ID}[button]
    assert casts == ([] if cancel else [(expected, inventory, (40.0, 50.0, 0.0))])
    assert menu.target_item is None and values[mailbox + 60] == 0


@pytest.mark.parametrize('stage,reason', [(0, 'mission validation'), (8, 'paradrop object type'), (9, 'restart Zero Hour after asset installation')])
def test_native_ability_rejection_reports_the_failed_stage(stage, reason):
    from zh.consumables import CombatEffects
    sim = PatriotSimulation()
    sim.put(sim.mailbox, 3)
    sim.put(sim.mailbox + a.STAGE, stage)
    sim.put(sim.mailbox + a.DETAIL, 0x9484AC)
    game = SimpleNamespace(base=sim.base, pointer=sim.get)
    effect = CombatEffects(game)
    effect.mailbox, effect.operation, effect.reported = sim.mailbox, 6, False
    report = effect.poll()[0]
    assert reason in report and 'cooldown restored' in report
    if stage == 8:
        assert '0x9484ac' in report and '0x948570' in report
    assert effect.ability_result == (6, 3)


def test_base_creation_object_is_rejected_before_clone_or_spawn():
    sim = PatriotSimulation()
    sim.put(sim.nugget, 0x9484AC)  # base class is not a DeliverPayloadNugget
    sim.run()
    assert sim.get(sim.mailbox) == 3 and not sim.drops
    assert sim.get(sim.mailbox + a.STAGE) == 8
    assert sim.get(sim.mailbox + a.DETAIL) == 0x9484AC
    assert sim.get(sim.patriot + 0x6C) == 0x1020


@pytest.mark.parametrize('first,second', [(11, 13), (13, 11)])
def test_changed_target_kind_clears_only_previous_owned_preview(first, second):
    from zh.unlock_menu import RADIUS_TYPE
    sim = TargetSimulation()
    sim.put(sim.mailbox + 120, first)
    sim.tick(); sim.put(sim.mailbox + 60, 1); sim.tick()
    assert sim.get(sim.ui + RADIUS_TYPE) == first
    assert sim.get(sim.mailbox + 124) == first
    sim.put(sim.mailbox + 120, second); sim.tick()
    assert sim.get(sim.mailbox + 60) == 3
    assert sim.get(sim.ui + RADIUS_TYPE) == 0
    assert sim.cursor_calls.count('clear') == 1
    sim.put(sim.mailbox + 60, 1); sim.tick()
    assert sim.get(sim.ui + RADIUS_TYPE) == second
