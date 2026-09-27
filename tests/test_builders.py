import struct
from itertools import combinations

import pytest

from zh.builders import BuilderUnlock, BUTTON_NAMES, MENUS
from zh.dozer import GAME_LOGIC_RVA, CONTROL_BAR_RVA
from zh.detector import Snapshot
from zh.memory import MemoryReadError
from zh.mission_data import BUILDER_ITEMS, MISSIONS


class Game:
    base, logic, bar = 0x400000, 0x20000, 0x30000

    def __init__(self):
        self.state = Snapshot('usa', 'mission01', 'maps/md_usa01/md_usa01.map', False)
        self.values = {self.base + GAME_LOGIC_RVA: self.logic,
                       self.base + CONTROL_BAR_RVA: self.bar,
                       self.logic + 0x94: 0, self.logic + 0x24: 0,
                       self.logic + 0x28: 0}
        self.strings, self.writes = {}, []
        self.buttons = {}
        button_names = (*BUTTON_NAMES, 'command_setrallypoint', 'command_sell', 'command_artillerybarrage')
        for i, name in enumerate(button_names):
            pointer = 0x50000 + i * 0x100
            self.buttons[name] = pointer
            self.strings[pointer + 0xC] = name
            self.values[pointer + 4] = 0
            self.values[pointer + 0x14] = pointer + 0x100 if i < len(button_names) - 1 else 0
        self.values[self.bar + 0x28] = 0x50000
        self.sets = {}
        for i, (name, slots) in enumerate(MENUS.items()):
            pointer = 0x60000 + i * 0x100
            self.sets[name] = pointer
            self.strings[pointer + 0xC] = name
            self.values[pointer + 4] = 0
            self.values[pointer + 0x58] = pointer + 0x100 if i < len(MENUS) - 1 else 0
            for slot in range(18):
                self.values[pointer + 0x10 + slot * 4] = 0
            native = 0 if name.startswith('america') else 1 if name.startswith('china') else 2
            self.values[pointer + 0x10] = self.buttons[BUTTON_NAMES[native]]
            self.values[pointer + 0x10 + 12 * 4] = self.buttons['command_setrallypoint']
            self.values[pointer + 0x10 + 13 * 4] = self.buttons['command_sell']
        self.values[self.bar + 0x2C] = 0x60000

    def snapshot(self):
        return self.state

    def pointer(self, address):
        return self.values[address]

    def string(self, address):
        return self.strings[address]

    def read(self, address, size):
        assert size == 8
        return struct.pack('<II', self.pointer(address), self.pointer(address + 4))

    def replace_pointer(self, address, expected, replacement):
        assert self.pointer(address) == expected
        self.writes.append((address, expected, replacement))
        self.values[address] = replacement

    def add_override(self, name, slot, value=0):
        self.values[self.logic + 0x24] = 0x70000
        self.values[self.logic + 0x28] = 0x70004
        self.values[0x70000] = 0x71000
        self.values[0x71000] = 0
        self.strings[0x71004] = chr(ord('0') + slot) + name
        self.values[0x71008] = value
        return 0x71008


INVENTORIES = [set(c) for count in range(4) for c in combinations(BUILDER_ITEMS, count)]


@pytest.mark.parametrize('owned', INVENTORIES)
def test_all_inventory_combinations_enable_only_owned_builders_on_every_menu(owned):
    game = Game()
    original = game.values.copy()
    adapter = BuilderUnlock(game)
    adapter.apply(owned)
    ids = tuple(BUILDER_ITEMS)
    touched = set()
    for name, slots in MENUS.items():
        for i, slot in enumerate(slots):
            address = game.sets[name] + 0x10 + slot * 4
            touched.add(address)
            assert game.pointer(address) == (game.buttons[BUTTON_NAMES[i]] if ids[i] in owned else 0)
    assert all(game.values[k] == v for k, v in original.items() if k not in touched)
    writes = len(game.writes)
    adapter.apply(owned)
    assert len(game.writes) == writes
    adapter.restore()
    assert game.values == original


@pytest.mark.parametrize('mission', MISSIONS, ids=lambda m: m['key'])
def test_each_stock_campaign_mission_is_eligible(mission):
    game = Game()
    game.state = Snapshot(mission['campaign'], mission['mission'], mission['map'], False)
    BuilderUnlock(game).apply(set(BUILDER_ITEMS))
    assert game.writes


@pytest.mark.parametrize('state', [Snapshot(), Snapshot('usa', 'mission01', 'maps/custom.map'),
                                  Snapshot('usa', 'mission01', 'maps/md_usa01/md_usa01.map', True), None])
def test_ineligible_or_incoherent_state_never_applies_unlocks(state):
    game = Game()
    game.state = state
    BuilderUnlock(game).apply(set(BUILDER_ITEMS))
    assert not game.writes


@pytest.mark.parametrize('mode', range(1, 7))
def test_no_unlocks_in_other_modes(mode):
    game = Game()
    game.values[game.logic + 0x94] = mode
    BuilderUnlock(game).apply(set(BUILDER_ITEMS))
    assert not game.writes


def test_campaign_remove_button_override_is_updated_and_restored():
    game = Game()
    address = game.add_override('americacommandcentercommandset', 0)
    original = game.values.copy()
    adapter = BuilderUnlock(game)
    adapter.apply(set(BUILDER_ITEMS))
    assert game.pointer(address) == game.buttons[BUTTON_NAMES[0]]
    adapter.restore()
    assert game.values == original


def test_inventory_removed_relocks_all_builders_and_cleanup_recovers_originals():
    game = Game()
    original = game.values.copy()
    adapter = BuilderUnlock(game)
    adapter.apply(set(BUILDER_ITEMS))
    adapter.apply(set())
    for name, slots in MENUS.items():
        assert all(game.pointer(game.sets[name] + 0x10 + slot * 4) == 0 for slot in slots)
    adapter.restore()
    assert game.values == original


def test_return_to_menu_restores_persistent_command_sets():
    game = Game()
    original = game.values.copy()
    adapter = BuilderUnlock(game)
    adapter.apply(set(BUILDER_ITEMS))
    game.state = Snapshot()
    adapter.apply(set(BUILDER_ITEMS))
    assert game.values == original


def test_freed_campaign_override_is_not_written_during_cleanup():
    game = Game()
    address = game.add_override('americacommandcentercommandset', 0)
    adapter = BuilderUnlock(game)
    adapter.apply(set(BUILDER_ITEMS))
    game.values[0x70000] = 0
    game.values[address] = 0xDEADBEEF
    count = len(game.writes)
    adapter.restore()
    assert all(write[0] != address for write in game.writes[count:])


def test_unexpected_slot_prevents_partial_update():
    game = Game()
    name = 'glacommandcentercommandset'
    game.values[game.sets[name] + 0x10 + 2 * 4] = game.buttons['command_artillerybarrage']
    with pytest.raises(MemoryReadError, match='Unexpected builder'):
        BuilderUnlock(game).apply(set(BUILDER_ITEMS))
    assert not game.writes


def test_transition_before_first_write_is_rechecked():
    game = Game()
    states = iter([game.state, Snapshot()])
    game.snapshot = lambda: next(states)
    BuilderUnlock(game).apply(set(BUILDER_ITEMS))
    assert not game.writes


def test_changed_slot_during_cleanup_is_left_alone():
    game = Game()
    adapter = BuilderUnlock(game)
    adapter.apply(set(BUILDER_ITEMS))
    address = game.sets['americacommandcentercommandset'] + 0x10 + 2 * 4
    game.values[address] = 0xDEADBEEF
    adapter.restore()
    assert game.pointer(address) == 0xDEADBEEF


def test_map_override_cloned_after_unlock_restores_both_live_menu_nodes():
    game = Game()
    name = 'americacommandcentercommandset'
    base = game.sets[name]
    before = {slot: game.pointer(base + 0x10 + 4 * slot) for slot in MENUS[name]}
    adapter = BuilderUnlock(game)
    adapter.apply(set(BUILDER_ITEMS))
    clone = 0x80000
    game.strings[clone + 0xC] = name
    game.values[clone + 4] = 0
    for slot in range(18):
        game.values[clone + 0x10 + slot * 4] = game.pointer(base + 0x10 + slot * 4)
    game.values[base + 4] = clone
    adapter.apply(set(BUILDER_ITEMS))
    adapter.restore()
    for pointer in (base, clone):
        assert all(game.pointer(pointer + 0x10 + slot * 4) == value for slot, value in before.items())
