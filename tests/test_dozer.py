import struct

import pytest

from zh.detector import Snapshot
from zh.dozer import DozerUnlock, GAME_LOGIC_RVA, CONTROL_BAR_RVA, COMMAND_SET, COMMAND_BUTTON, MISSION_MAP
from zh.memory import MemoryReadError


class Game:
    base = 0x400000
    logic, bar, command_set, button = 0x20000, 0x40000, 0x41000, 0x42000
    buckets, node = 0x30000, 0x31000

    def __init__(self):
        self.values = {
            self.base + GAME_LOGIC_RVA: self.logic,
            self.base + CONTROL_BAR_RVA: self.bar,
            self.logic + 0x94: 0,
            self.logic + 0x24: self.buckets,
            self.logic + 0x28: self.buckets + 4,
            self.buckets: self.node,
            self.node: 0, self.node + 8: 0,
            self.bar + 0x2C: self.command_set,
            self.command_set + 4: 0,
            self.command_set + 0x10: self.button,
            self.command_set + 0x58: 0,
            self.button + 4: 0,
        }
        self.strings = {self.node + 4: '0' + COMMAND_SET,
                        self.command_set + 0xC: COMMAND_SET,
                        self.button + 0xC: COMMAND_BUTTON}
        self.state = Snapshot('usa', 'mission01', MISSION_MAP, False)
        self.writes = []

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
        assert self.values[address] == expected
        self.writes.append((address, expected, replacement))
        self.values[address] = replacement


def test_item_restores_only_existing_dozer_slot_and_cleanup_relocks():
    game = Game()
    adapter = DozerUnlock(game)
    adapter.apply(False)
    assert not game.writes
    before = game.values.copy()
    assert 'unlocked' in adapter.apply(True)
    assert game.writes == [(game.node + 8, 0, game.button)]
    assert {key for key in before if before[key] != game.values[key]} == {game.node + 8}
    adapter.apply(True)
    assert len(game.writes) == 1
    adapter.restore()
    assert game.values == before


@pytest.mark.parametrize('state', [None, Snapshot(),
    Snapshot('usa', 'mission02', 'maps/md_usa02/md_usa02.map', False),
    Snapshot('gla', 'mission01', MISSION_MAP, False),
    Snapshot('usa', 'mission01', 'maps/custom/custom.map', False)])
def test_other_missions_and_transitions_never_write(state):
    game = Game()
    game.state = state
    DozerUnlock(game).apply(True)
    assert not game.writes


@pytest.mark.parametrize('mode', [1, 2, 3, 4, 5, 6])
def test_only_single_player_mode_can_write(mode):
    game = Game()
    game.values[game.logic + 0x94] = mode
    DozerUnlock(game).apply(True)
    assert not game.writes


def test_missing_override_is_not_created():
    game = Game()
    game.values[game.buckets] = 0
    assert 'waiting' in DozerUnlock(game).apply(True)
    assert not game.writes


@pytest.mark.parametrize('bad', ['command', 'value', 'buckets', 'cycle'])
def test_unrecognized_layout_fails_without_writing(bad):
    game = Game()
    if bad == 'command':
        game.strings[game.button + 0xC] = 'another_command'
    elif bad == 'value':
        game.values[game.node + 8] = 0xABCDE
    elif bad == 'buckets':
        game.values[game.logic + 0x28] = game.buckets - 4
    else:
        game.strings[game.node + 4] = 'other_key'
        game.values[game.node] = game.node
    with pytest.raises(MemoryReadError):
        DozerUnlock(game).apply(True)
    assert not game.writes


def test_mission_change_between_lookup_and_write_is_rechecked():
    game = Game()
    states = iter([game.state, Snapshot()])
    game.snapshot = lambda: next(states)
    assert 'changing' in DozerUnlock(game).apply(True)
    assert not game.writes


def test_cleanup_does_not_touch_another_mission():
    game = Game()
    adapter = DozerUnlock(game)
    adapter.apply(True)
    game.state = Snapshot('usa', 'mission02', 'maps/md_usa02/md_usa02.map', False)
    adapter.restore()
    assert len(game.writes) == 1


def test_authoritative_inventory_removal_relocks_the_button():
    game = Game()
    game.values[game.node + 8] = game.button
    DozerUnlock(game).apply(False)
    assert game.writes == [(game.node + 8, game.button, 0)]
