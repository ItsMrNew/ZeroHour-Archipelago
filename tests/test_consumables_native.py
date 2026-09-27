import struct
from types import SimpleNamespace

import pytest
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP

from test_power import Simulation, InstallGame
from zh import consumables as c
from zh import reinforcements as r
from zh.power import build_stub


class CombatSimulation(Simulation):
    instruction_budget = 15000
    anchor, template, assistant, factory = 0x2206000, 0x2208000, 0x2209000, 0x220A000

    def __init__(self, operation=1):
        self.native_calls = []
        self.operation = operation
        self.rf_failure = None
        self.objects = {}
        self.promoted = []
        self.loaded = []
        self.destroyed = []
        self.occupied = set()
        self.current_template_name = '' 
        self.kinds = {14}
        self.legal = True
        super().__init__()
        self.uc.mem_map(0x2300000, 0x20000)
        self.put(self.player + 0x160, self.player + 0x400)
        self.uc.mem_write(self.mailbox + r.NAMES, b''.join(n.encode().ljust(48, b'\0') for n in r.RECIPE))
        self.uc.mem_write(self.code, build_stub(self.base, self.code, self.mailbox, True))
        self.uc.mem_write(self.code + c.PRODUCTION_CODE_OFFSET,
                         c.build_production_stub(self.base, self.code + c.PRODUCTION_CODE_OFFSET, self.mailbox))
        for rva, pop in ((c.ASCII_CTOR_RVA, 4), (c.ASCII_DTOR_RVA, 0),
                         (c.FIND_TEMPLATE_RVA, 8), (c.BUILD_RVA, 20),
                         (c.LEGAL_RVA, 24), (c.KINDOF_RVA, 4), (c.GET_OWNER_RVA, 0),
                         (r.PROMOTE_RVA, 8), (r.NEW_OBJECT_RVA, 16), (r.SET_POSITION_RVA, 4),
                         (r.VALID_CONTAINER_RVA, 8), (r.ADD_PASSENGER_RVA, 4), (r.DESTROY_RVA, 4)):
            self.uc.mem_write(self.base + rva, bytes((0xC2, pop, 0)))
        # Real visitor callback invocation, so stack discipline and local branch
        # relocation are exercised instead of simply manufacturing an anchor.
        iterate = bytes.fromhex('8b4424048b5424085268') + struct.pack('<I', self.anchor)
        iterate += bytes.fromhex('ffd083c408c20800')
        self.uc.mem_write(self.base + c.ITERATE_RVA, iterate)
        self.put(self.base + c.ASSISTANT_RVA, self.assistant)
        self.put(self.base + c.FACTORY_RVA, self.factory)
        self.put(self.mailbox + 28, operation)
        self.uc.mem_write(self.anchor + 0x38, struct.pack('<fff', 500, 600, 0))
        self.uc.mem_write(self.mailbox + c.OFFSETS, b''.join(struct.pack('<ff', *p) for p in c.PLACEMENTS))
        self.uc.mem_write(self.mailbox + 32, b'AmericaInfantryRanger\0')

    def observe(self, uc, address, size, user_data):
        super().observe(uc, address, size, user_data)
        this, sp = uc.reg_read(UC_X86_REG_ECX), uc.reg_read(UC_X86_REG_ESP)
        rva = address - self.base
        pops = {c.ASCII_CTOR_RVA:1, c.ASCII_DTOR_RVA:0, c.FIND_TEMPLATE_RVA:2,
                c.BUILD_RVA:5, c.LEGAL_RVA:6, c.KINDOF_RVA:1, c.GET_OWNER_RVA:0}
        if self.operation == 1:
            pops.update({r.PROMOTE_RVA: 2, r.NEW_OBJECT_RVA: 4, r.SET_POSITION_RVA: 1,
                         r.VALID_CONTAINER_RVA: 2, r.ADD_PASSENGER_RVA: 1, r.DESTROY_RVA: 1})
        if rva not in pops:
            return
        args = [self.get(sp + 4 + i*4) for i in range(pops[rva])]
        self.native_calls.append((rva, this, args))
        result = 0
        if rva == c.ASCII_CTOR_RVA:
            self.current_template_name = bytes(uc.mem_read(args[0], 48)).split(b'\0')[0].decode()
        elif rva == c.FIND_TEMPLATE_RVA:
            assert this == self.factory
            assert args == [self.mailbox + c.STRING, 0]
            result = self.template
            if self.operation == 1:
                result += r.RECIPE.index(self.current_template_name) * 0x100
                if self.rf_failure == self.current_template_name:
                    result = 0
        elif rva == c.KINDOF_RVA:
            assert this == self.anchor
            result = int(args[0] in self.kinds)
        elif rva == c.LEGAL_RVA:
            assert this == self.assistant
            assert args[0] == self.mailbox + c.POS and args[1] in (self.template, self.template + 0x100)
            assert args[2:] == [0, 0x17, self.anchor, self.player]
            position = bytes(uc.mem_read(self.mailbox + c.POS, 12))
            result = int(not self.legal or position in self.occupied or (self.rf_failure == 'vehicle_ground' and args[1] == self.template))
        elif rva == c.BUILD_RVA:
            assert this == self.assistant
            assert args[0] == 0 and args[1] in (self.template, self.template + 0x100)
            assert args[2:] == [self.mailbox + c.POS, 0, self.player]
            result = 0 if self.rf_failure == 'build' else self.create_object(args[1])
            if result:
                self.occupied.add(bytes(uc.mem_read(self.mailbox + c.POS, 12)))
        elif rva == r.NEW_OBJECT_RVA:
            assert this == self.factory and args == [self.template + 0x200, self.player + 0x400, 0, 0]
            result = 0 if self.rf_failure == 'passenger_create' else self.create_object(args[0])
        elif rva == r.SET_POSITION_RVA:
            assert this in self.objects and args == [self.mailbox + c.POS]
        elif rva == r.PROMOTE_RVA:
            obj = this - 0x400
            assert obj in self.objects and args == [3, 0]
            assert self.objects[obj] != self.template + 0x100  # CIA agents retain their stock rank
            if self.rf_failure != 'promotion':
                self.put(this + 12, 3)
                self.promoted.append(obj)
        elif rva == r.VALID_CONTAINER_RVA:
            assert self.objects[this - 0x500] == self.template
            assert args[0] in self.promoted and args[1] == 1
            result = int(self.rf_failure != 'capacity' and len(self.loaded) < 5)
        elif rva == r.ADD_PASSENGER_RVA:
            vehicle = this - 0x500
            assert args[0] in self.promoted and vehicle in self.promoted
            if self.rf_failure != 'contain':
                self.put(args[0] + r.CONTAINED_BY_OFFSET, vehicle)
                self.loaded.append(args[0])
        elif rva == r.DESTROY_RVA:
            assert this == self.logic and args[0] in self.objects
            self.destroyed.append(args[0])
        elif rva == c.GET_OWNER_RVA:
            result = self.owner
        uc.reg_write(UC_X86_REG_EAX, result)
        uc.reg_write(UC_X86_REG_ECX, 0xBAD)
        uc.reg_write(UC_X86_REG_EDX, 0xBAD)

    def create_object(self, template):
        obj = 0x2300000 + len(self.objects) * 0x1000
        self.objects[obj] = template
        tracker, contain = obj + 0x400, obj + 0x500
        self.put(obj + r.EXPERIENCE_OFFSET, tracker)
        self.put(tracker, self.base + r.EXPERIENCE_TABLE_RVA)
        self.put(obj + r.CONTAIN_OFFSET, contain)
        self.put(contain, self.base + r.CONTAIN_TABLE_RVA if self.rf_failure != 'container_layout' else 0)
        self.put(contain - 0x14, obj)
        return obj


def test_reinforcements_create_cia_escort_and_heroic_loaded_humvee():
    sim = CombatSimulation()
    sim.run()
    assert sim.get(sim.mailbox) == 2
    assert sim.get(sim.mailbox + 24) == 9
    calls = [rva for rva, _, _ in sim.native_calls]
    assert calls.count(c.BUILD_RVA) == 4
    assert calls.count(r.NEW_OBJECT_RVA) == 5
    assert calls.count(c.ASCII_DTOR_RVA) == 3
    assert len(sim.promoted) == 6 and len(sim.loaded) == 5
    assert not sim.destroyed
    assert sim.get(sim.mailbox + r.AGENT_COUNT) == 3
    assert sim.get(sim.mailbox + r.VEHICLE_COUNT) == 1
    assert sim.get(sim.mailbox + r.PASSENGER_COUNT) == 5
    assert sum(t == sim.template + 0x100 for t in sim.objects.values()) == 3
    sim.run()
    assert len(sim.native_calls) == len(calls)  # no replay


@pytest.mark.parametrize('kinds', [{8}, {9}])
def test_infantry_or_vehicle_can_anchor_without_command_center(kinds):
    sim = CombatSimulation()
    sim.kinds = kinds
    sim.run()
    assert sim.get(sim.mailbox + 24) == 9


@pytest.mark.parametrize('failure', r.RECIPE)
def test_missing_recipe_template_prevents_any_partial_creation(failure):
    sim = CombatSimulation()
    sim.rf_failure = failure
    sim.run()
    assert sim.get(sim.mailbox) == 3
    assert not sim.objects
    calls = [rva for rva, _, _ in sim.native_calls]
    assert calls.count(c.ASCII_CTOR_RVA) == calls.count(c.ASCII_DTOR_RVA)


@pytest.mark.parametrize('failure,counts,destroyed', [
    ('passenger_create', (3, 1, 0), 0),
    ('capacity', (3, 1, 0), 5),
    ('contain', (3, 1, 0), 5),
    ('promotion', (3, 0, 0), 1),
    ('container_layout', (3, 0, 0), 1),
    ('vehicle_ground', (3, 0, 0), 0),
    ('build', (0, 0, 0), 0),
])
def test_partial_delivery_is_bounded_and_failed_units_are_cleaned_up(failure, counts, destroyed):
    sim = CombatSimulation()
    sim.rf_failure = failure
    sim.run()
    assert sim.get(sim.mailbox) == 2
    assert tuple(sim.get(sim.mailbox + off) for off in (r.AGENT_COUNT, r.VEHICLE_COUNT, r.PASSENGER_COUNT)) == counts
    assert sim.get(sim.mailbox + 24) == sum(counts)
    assert len(sim.destroyed) == destroyed
    assert len(sim.objects) - len(sim.destroyed) == sum(counts)
    previous = len(sim.native_calls)
    sim.run()
    assert len(sim.native_calls) == previous


@pytest.mark.parametrize('change', ['team', 'player', 'mission', 'loading'])
def test_reinforcements_never_spawn_during_transition_or_for_changed_player(change):
    sim = CombatSimulation()
    address = {'team': sim.player + 0x160, 'player': sim.players + 12,
               'mission': sim.manager + 12, 'loading': sim.logic + 0x51}[change]
    sim.put(address, 1 if change == 'loading' else 0)
    sim.run()
    assert sim.get(sim.mailbox) == 3
    assert not sim.objects


def test_full_and_partial_reports_include_actual_loaded_passenger_count():
    sim = CombatSimulation()
    sim.run()
    effect = c.CombatEffects(SimpleNamespace(pointer=sim.get))
    effect.mailbox, effect.operation, effect.reported = sim.mailbox, 1, False
    message, = effect.poll()
    assert '3/3 CIA Agents, 1/1 Heroic Humvee with 5/5 Heroic Missile Defenders loaded' in message
    assert effect.poll() == []
    sim.put(sim.mailbox + r.PASSENGER_COUNT, 2)
    effect.reported = False
    assert 'Partial delivery' in effect.poll()[0]


def test_callback_and_extra_data_fit_the_existing_allocation():
    code = build_stub(0x400000, 0x2000000, 0x2002000, True)
    assert len(code) < c.PRODUCTION_CODE_OFFSET
    production = c.build_production_stub(0x400000, 0x2000000 + c.PRODUCTION_CODE_OFFSET, 0x2002000)
    assert c.PRODUCTION_CODE_OFFSET + len(production) <= 0x1000
    assert r.ATTEMPTS + 4 <= 0x1000


@pytest.mark.parametrize('kind', ['dead', 'off_map', 'aircraft', 'no_ground'])
def test_no_spawn_in_invalid_or_obstructed_locations(kind):
    sim = CombatSimulation()
    if kind in ('dead', 'off_map'):
        sim.uc.mem_write(sim.anchor + 0x277, bytes([1 if kind == 'dead' else 8]))
    elif kind == 'aircraft':
        sim.kinds = {9, 10}
    else:
        sim.legal = False
    sim.run()
    assert sim.get(sim.mailbox + 24) == 0
    assert not any(r == c.BUILD_RVA for r, _, _ in sim.native_calls)
    if kind == 'no_ground':
        assert sum(r == c.LEGAL_RVA for r, _, _ in sim.native_calls) == 96


def test_shutdown_extends_and_expires_on_simulation_frames():
    sim = CombatSimulation(2)
    sim.put(sim.mailbox + 12, 600)
    sim.run()
    assert sim.get(sim.mailbox + c.TIMER) == 900
    assert sim.get(sim.mailbox) == 2
    sim.put(sim.mailbox, 1)
    sim.run()
    assert sim.get(sim.mailbox + c.TIMER) == 1500
    sim.put(sim.logic + 0x3C, 1499)
    sim.run()
    assert sim.get(sim.mailbox + c.TIMER) == 1500
    sim.put(sim.logic + 0x3C, 1500)
    sim.run()
    assert sim.get(sim.mailbox + c.TIMER) == 0


@pytest.mark.parametrize('change', ['loading', 'save', 'newgame', 'rewind', 'mission', 'player', 'mode'])
def test_shutdown_clears_at_mission_transitions(change):
    sim = CombatSimulation(2)
    sim.run()
    changes = {'loading':(sim.logic + 0x51, 1), 'save':(sim.logic + 0x52, 1),
        'newgame':(sim.logic + 0x64, 1), 'rewind':(sim.logic + 0x3C, 299),
        'mission':(sim.manager + 12, sim.mission + 4), 'player':(sim.players + 12, 0),
        'mode':(sim.logic + 0x94, 1)}
    sim.put(*changes[change])
    sim.run()
    assert sim.get(sim.mailbox + c.TIMER) == 0


@pytest.mark.parametrize('case', ['own_unit', 'enemy', 'upgrade', 'empty', 'expired', 'loading', 'rewind'])
def test_production_dispatcher_only_pauses_own_unit_queue(case):
    sim = CombatSimulation(2)
    sim.put(sim.mailbox + 12, 600)
    sim.run()
    interface, entry, obj = 0x220B000, 0x220C000, sim.anchor
    sim.put(interface + 0x18, entry if case != 'empty' else 0)
    sim.put(entry + 4, 2 if case == 'upgrade' else 1)
    sim.put(interface - 8, obj)
    sim.owner = sim.player if case != 'enemy' else sim.player + 4
    if case == 'expired': sim.put(sim.logic + 0x3C, 900)
    if case == 'rewind': sim.put(sim.logic + 0x3C, 200)
    if case == 'loading': sim.put(sim.logic + 0x52, 1)
    sim.put(sim.stack, sim.code + 0xF00)
    sim.uc.reg_write(UC_X86_REG_ECX, interface)
    sim.uc.reg_write(UC_X86_REG_ESP, sim.stack)
    # Native original returns 123, whereas paused wrapper returns sleep=1.
    sim.uc.mem_write(sim.base + c.PRODUCTION_UPDATE_RVA, bytes.fromhex('b87b000000c3'))
    sim.uc.emu_start(sim.code + c.PRODUCTION_CODE_OFFSET, sim.code + 0xF00, count=500)
    assert sim.uc.reg_read(UC_X86_REG_EAX) == (1 if case == 'own_unit' else 123)
    assert sim.uc.reg_read(UC_X86_REG_ESP) == sim.stack + 4
    assert sim.get(interface + 0x18) == (entry if case != 'empty' else 0)


def test_extended_hook_still_applies_power_trap():
    sim = CombatSimulation(0)
    sim.run()
    assert sim.calls == [(sim.player, 1)]
    assert sim.get(sim.player + 0x8C) == 1200


def test_installer_shares_logic_hook_restores_production_table_and_keeps_data_nonexecutable():
    game = InstallGame(0x567B98)
    for rva, prefix in (*c.NATIVE_SIGNATURES, *r.SIGNATURES, *c.sell_building.SIGNATURES):
        game.store(game.base + rva, bytes.fromhex(prefix))
    table = game.base + c.PRODUCTION_TABLE_RVA
    game.store(table, struct.pack('<II', game.base + c.PRODUCTION_UPDATE_RVA, game.base + 0x1A0390))
    def protect(handle, address, size, protection, previous):
        previous._obj.value = 2 if protection == 4 else 4
        return game.protect(handle, address, size, protection, previous)
    game.api.VirtualProtectEx = protect
    effect = c.CombatEffects(game)
    state = SimpleNamespace(logic=game.logic, player=game.player, frame=300, mission=('usa','mission01'))
    effect.prepare(state, 1, 2)
    assert game.allocations == 1
    assert game.pointer(table) == effect.region + c.PRODUCTION_CODE_OFFSET
    assert game.pointer(effect.mailbox + 12) == 600
    assert game.pointer(effect.mailbox + 28) == 2
    assert game.protections[-2:] == [(table,4,4),(table,4,2)]
    effect.close()
    assert game.pointer(table) == game.base + c.PRODUCTION_UPDATE_RVA
    assert game.pointer(game.logic) == game.original
    assert game.pointer(effect.mailbox + c.TIMER) == 0


@pytest.mark.parametrize('operation', [0, 1, 2])
def test_native_effects_wait_for_control_at_execution_time(operation):
    from zh.gameplay import INPUT_OFFSET
    sim = CombatSimulation(operation)
    if operation == 2: sim.put(sim.mailbox + 12, 600)
    sim.put(0x220D000 + INPUT_OFFSET, 0)
    for frame in (300, 900, 2400):
        sim.put(sim.logic + 0x3C, frame)
        sim.run()
        assert sim.get(sim.mailbox) == 1
        assert not sim.native_calls and not sim.calls
        assert sim.get(sim.mailbox + c.TIMER) == 0
    sim.put(0x220D000 + INPUT_OFFSET, 1)
    sim.run()
    assert sim.get(sim.mailbox) == 2
    if operation == 2: assert sim.get(sim.mailbox + c.TIMER) == 3000
