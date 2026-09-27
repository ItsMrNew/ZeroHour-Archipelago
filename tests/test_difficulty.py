import struct
from types import SimpleNamespace

import pytest

from zh.difficulty import (inspect_difficulty, GAME_LOGIC_RVA, SCRIPT_ENGINE_RVA,
                           SCRIPT_VTABLE_RVA, SCRIPT_DIFFICULTY_OFFSET)
from zh.memory import MemoryReadError, CAMPAIGN_GLOBAL_RVA, CAMPAIGN_VTABLE_RVA


class FakeGame:
    base = 0x400000

    def __init__(self, campaign=0, active=0):
        self.data = {}
        for address, value in [(self.base + GAME_LOGIC_RVA, 0x10000),
                               (self.base + CAMPAIGN_GLOBAL_RVA, 0x20000),
                               (self.base + SCRIPT_ENGINE_RVA, 0x30000),
                               (0x10094, 0), (0x1003C, 300),
                               (0x20000, self.base + CAMPAIGN_VTABLE_RVA),
                               (0x30000, self.base + SCRIPT_VTABLE_RVA),
                               (0x30000 + SCRIPT_DIFFICULTY_OFFSET, active)]:
            self.data[address] = struct.pack('<i', value)
        self.data.update({0x10051: b'\0\0', 0x10064: b'\0',
                          0x20008: struct.pack('<5i', 123, 456, 0, 5000, campaign)})

    def read(self, address, size):
        data = self.data[address]
        assert len(data) == size
        return data

    def pointer(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def snapshot(self):
        return SimpleNamespace(campaign='usa', mission='mission01', map_name='maps/md_usa01/md_usa01.map')


@pytest.mark.parametrize('difficulty', range(3))
def test_reads_loaded_and_active_difficulty(difficulty):
    assert inspect_difficulty(FakeGame(difficulty, difficulty)) == ('USA Mission 01', difficulty, difficulty)


def test_disagreement_is_exposed_not_masked_by_campaign_setting():
    assert inspect_difficulty(FakeGame(0, 2))[1:] == (0, 2)


@pytest.mark.parametrize('address,data', [
    (0x10051, b'\1\0'), (0x10094, struct.pack('<i', 1)),
    (0x30000, struct.pack('<i', 0)),
    (0x30000 + SCRIPT_DIFFICULTY_OFFSET, struct.pack('<i', 3)),
])
def test_rejects_loading_non_campaign_wrong_layout_and_unknown_difficulty(address, data):
    game = FakeGame()
    game.data[address] = data
    with pytest.raises(MemoryReadError):
        inspect_difficulty(game)


def test_rejects_transition_between_reads():
    game = FakeGame()
    original = game.snapshot
    def transition():
        game.data[0x10051] = b'\1\0'
        return original()
    game.snapshot = transition
    with pytest.raises(MemoryReadError, match='changed'):
        inspect_difficulty(game)
