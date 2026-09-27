import struct
from itertools import product

import pytest

from zh.builder_selection import SelectableBuilders, GENERAL_MENUS, choices, FAMILIES
from zh.mission_data import BUILDER_CATALOG, ALL_MISSIONS
from zh.detector import Snapshot
from zh.memory import MemoryReadError
from test_builders import Game


class GeneralGame(Game):
    def __init__(self):
        super().__init__()
        # Populate all real general menus, preserving unrelated power buttons.
        self.buttons, self.sets = {}, {}
        names = [entry[2] for entry in BUILDER_CATALOG.values()] + ['command_setrallypoint', 'command_sell', 'demo_command_tertiarysuicide']
        for i, name in enumerate(names):
            pointer = 0x80000 + i * 0x100
            self.buttons[name] = pointer
            self.strings[pointer + 0xC] = name
            self.values[pointer + 4] = 0
            self.values[pointer + 0x14] = pointer + 0x100 if i + 1 < len(names) else 0
        self.values[self.bar + 0x28] = 0x80000
        for i, (name, slots) in enumerate(GENERAL_MENUS.items()):
            pointer = 0x90000 + i * 0x100
            self.sets[name] = pointer
            self.strings[pointer + 0xC] = name
            self.values[pointer + 4] = 0
            self.values[pointer + 0x58] = pointer + 0x100 if i + 1 < len(GENERAL_MENUS) else 0
            for slot in range(18): self.values[pointer + 0x10 + slot * 4] = 0xDEAD  # powers must be untouched
            for slot in slots: self.values[pointer + 0x10 + slot * 4] = 0
            prefix = name.split('_')[0] + '_' if '_' in name else ''
            faction = 'america' if 'america' in name else 'china' if 'china' in name else 'gla'
            command = f'{prefix}command_construct{faction}' + ('worker' if faction == 'gla' else 'dozer')
            self.values[pointer + 0x10] = self.buttons[command]
            self.values[pointer + 0x10 + 12 * 4] = self.buttons['command_setrallypoint']
            self.values[pointer + 0x10 + 13 * 4] = self.buttons['command_sell']
            if name == 'demo_glacommandcentercommandsetupgrade':
                self.values[pointer + 0x10 + 2 * 4] = self.buttons['demo_command_tertiarysuicide']
        self.values[self.bar + 0x2C] = 0x90000
        self.loading = b'\0\0'
        self.new_game = b'\0'

    def read(self, address, size):
        if (address, size) == (self.logic + 0x51, 2): return self.loading
        if (address, size) == (self.logic + 0x64, 1): return self.new_game
        return super().read(address, size)


VARIANTS = [[item for item, entry in BUILDER_CATALOG.items() if entry[1] == family] for family in FAMILIES]


@pytest.mark.parametrize('selected', tuple(product(*VARIANTS)))
def test_every_builder_combination_on_all_command_centers_and_restoration(selected):
    game = GeneralGame(); old = game.values.copy(); adapter = SelectableBuilders(game)
    owned = set(BUILDER_CATALOG)
    adapter.apply_selection(owned, dict(zip(FAMILIES, selected)))
    touched = set()
    for name, slots in GENERAL_MENUS.items():
        for index, slot in enumerate(slots):
            address = game.sets[name] + 0x10 + 4 * slot
            touched.add(address)
            assert game.pointer(address) == game.buttons[BUILDER_CATALOG[selected[index]][2]]
    assert all(game.pointer(address) == value for address, value in old.items() if address not in touched)
    adapter.apply_selection(owned, dict.fromkeys(FAMILIES))
    assert all(game.pointer(address) == old[address] for address in touched)
    adapter.restore()
    assert game.values == old


@pytest.mark.parametrize('mission', ALL_MISSIONS, ids=lambda m: m['key'])
def test_builder_selection_recognizes_all_campaign_and_challenge_battles(mission):
    game = GeneralGame()
    game.state = Snapshot(mission['campaign'], mission['mission'], mission['map'], False)
    SelectableBuilders(game).apply_selection(set(BUILDER_CATALOG), {})
    assert game.writes


def test_unowned_variant_never_becomes_trainable():
    game = GeneralGame()
    old = game.values.copy()
    adapter = SelectableBuilders(game)
    adapter.apply_selection({VARIANTS[0][0]}, {'usa': VARIANTS[0][1]})
    for name, slots in GENERAL_MENUS.items():
        assert all(game.pointer(game.sets[name] + 0x10 + 4 * slot) == old[game.sets[name] + 0x10 + 4 * slot] for slot in slots)


def test_general_campaign_override_replaced_and_restored():
    game = GeneralGame()
    name = 'airf_americacommandcentercommandset'
    address = game.add_override(name, 0, 0)
    adapter = SelectableBuilders(game)
    adapter.apply_selection(set(BUILDER_CATALOG), {'usa':VARIANTS[0][2]})
    assert game.pointer(address) == game.buttons[BUILDER_CATALOG[VARIANTS[0][2]][2]]
    adapter.restore()
    assert game.pointer(address) == 0


def test_unexpected_general_command_is_rejected_before_any_write():
    game = GeneralGame()
    name = 'tank_chinacommandcentercommandset'
    game.values[game.sets[name] + 0x10 + 10 * 4] = game.buttons['command_sell']
    with pytest.raises(MemoryReadError, match='Unexpected'):
        SelectableBuilders(game).apply_selection(set(BUILDER_CATALOG), {})
    assert not game.writes


@pytest.mark.parametrize('loading,new_game', [(b'\1\0', b'\0'), (b'\0\1', b'\0'), (b'\0\0', b'\1')])
def test_builder_writes_wait_for_map_and_save_loads(loading, new_game):
    game = GeneralGame(); game.loading = loading; game.new_game = new_game
    SelectableBuilders(game).apply_selection(set(BUILDER_CATALOG), {})
    assert not game.writes


def test_turning_off_base_worker_restores_toxin_worker_and_empty_foreign_slots():
    game = GeneralGame()
    adapter = SelectableBuilders(game)
    worker = VARIANTS[2][0]
    name = 'chem_glacommandcentercommandset'
    address = game.sets[name] + 0x10
    original = game.pointer(address)
    restricted = game.add_override(name, 0, 0)
    adapter.apply_selection({worker}, {})
    assert game.pointer(address) == game.buttons['command_constructglaworker']
    assert game.pointer(restricted) == game.buttons['command_constructglaworker']
    adapter.apply_selection({worker}, {'gla': None})
    assert game.pointer(address) == original
    assert game.pointer(restricted) == 0  # preserve original mission restriction
    for foreign in ('americacommandcentercommandset', 'chinacommandcentercommandset'):
        slot = GENERAL_MENUS[foreign][2]
        expected = game.buttons['command_setrallypoint'] if foreign.startswith('china') else 0
        assert game.pointer(game.sets[foreign] + 0x10 + slot * 4) == expected
