import pytest

from zh.detector import Snapshot
from zh.effects import (PlayerEffects, PLAYER_LIST_RVA, GAME_LOGIC_RVA,
                        MONEY_VTABLE_RVA, ENERGY_VTABLE_RVA)
from zh.inventory import Inventory, ReceivedItem
from zh.memory import MemoryReadError
from zh.mission_data import CASH_ITEM_ID, POWER_TRAP_ID
from zh.state import Progress
from zh.gameplay import UI_RVA, UI_TABLE_RVA, INPUT_OFFSET


@pytest.fixture(autouse=True)
def simulation_power_queue(monkeypatch):
    """Immediate simulation stand-in; actual generated x86 is tested separately."""
    class Power:
        busy = False
        def __init__(self, game):
            self.game = game
        def prepare(self, state, count):
            self.state, self.count = state, count
        def arm(self):
            state = self.state
            address = state.player + 0x8C
            before = self.game.pointer(address)
            self.game.replace_pointer(address, before, max(state.frame, before) + self.count * 900)
        def poll(self):
            return []
        def close(self):
            pass
    monkeypatch.setattr('zh.effects.PowerOutage', Power)


class Game:
    base, logic, players, player = 0x400000, 0x20000, 0x30000, 0x40000

    def __init__(self):
        self.ui = 0x50000
        self.input = b'\1'
        self.values = {self.base + GAME_LOGIC_RVA: self.logic,
                       self.base + UI_RVA: self.ui, self.ui: self.base + UI_TABLE_RVA,
                       self.base + PLAYER_LIST_RVA: self.players,
                       self.logic + 0x3C: 300, self.logic + 0x94: 0,
                       self.players + 0xC: self.player, self.players + 0x10: 3,
                       self.players + 0x18: self.player,
                       self.player + 0x24: 1, self.player + 0x34: self.base + MONEY_VTABLE_RVA,
                       self.player + 0x38: 20000, self.player + 0x3C: 1,
                       self.player + 0x80: self.base + ENERGY_VTABLE_RVA,
                       self.player + 0x84: 20, self.player + 0x88: 10,
                       self.player + 0x8C: 0, self.player + 0x90: self.player}
        self.flags = b'\0\0'
        self.state = Snapshot('usa', 'mission01', 'maps/md_usa01/md_usa01.map', False)
        self.writes = []

    def pointer(self, address):
        return self.values[address]

    def read(self, address, size):
        if address == self.ui + INPUT_OFFSET and size == 1:
            return self.input
        assert address == self.logic + 0x51 and size == 2
        return self.flags

    def snapshot(self):
        return self.state

    def replace_pointer(self, address, expected, replacement):
        assert self.values[address] == expected
        self.writes.append((address, expected, replacement))
        self.values[address] = replacement


def inventory(*ids):
    return Inventory(ReceivedItem(item, index, 1, 0) for index, item in enumerate(ids))


def setup(tmp_path, *ids):
    game = Game()
    progress = Progress(tmp_path, 'effects', 0, 1)
    inv = inventory(*ids)
    progress.record_inventory(inv.items)
    return game, progress, inv, PlayerEffects(game, progress)


def load(game, adapter, inv, saved=False):
    game.flags = bytes((1, int(saved)))
    game.values[game.logic + 0x3C] = 0
    adapter.apply(inv)
    game.values[game.player + 0x38] = 20000
    game.flags = b'\0\0'
    game.values[game.logic + 0x3C] = 30
    messages = adapter.apply(inv)
    game.values[game.logic + 0x3C] = 60
    return messages + adapter.apply(inv)


def test_cash_receipt_adds_once_and_each_fresh_start_gets_cumulative_bonus(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID, CASH_ITEM_ID)
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == 30000
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == 30000
    for _ in range(2):
        load(game, adapter, inv)
        assert game.pointer(game.player + 0x38) == 30000
    restored = Progress(tmp_path, 'effects', 0, 1)
    PlayerEffects(game, restored).apply(inv)
    assert game.pointer(game.player + 0x38) == 30000


def test_save_load_and_midgame_attach_do_not_repeat_start_bonus(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    adapter.apply(inv)
    load(game, adapter, inv, saved=True)
    assert game.pointer(game.player + 0x38) == 20000
    PlayerEffects(game, progress).apply(inv)
    assert game.pointer(game.player + 0x38) == 20000


def test_receipt_during_load_not_double_counted(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    load(game, adapter, inv)
    assert game.pointer(game.player + 0x38) == 25000
    assert progress.effect_receipts == {0}


def test_power_uses_native_expiry_without_touching_production_or_consumption(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, POWER_TRAP_ID)
    adapter.apply(inv)
    assert game.writes == [(game.player + 0x8C, 0, 1200)]
    # Building changes remain in the untouched natural counters during the trap.
    game.values[game.player + 0x84] += 10
    game.values[game.player + 0x88] += 5
    game.values[game.logic + 0x3C] = 1201
    adapter.apply(inv)
    assert game.pointer(game.player + 0x84) == 30
    assert game.pointer(game.player + 0x88) == 15
    assert len(game.writes) == 1
    PlayerEffects(game, Progress(tmp_path, 'effects', 0, 1)).apply(inv)
    assert len(game.writes) == 1


def test_additional_traps_extend_existing_sabotage_timer(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, POWER_TRAP_ID, POWER_TRAP_ID)
    game.values[game.player + 0x8C] = 1000
    adapter.apply(inv)
    assert game.pointer(game.player + 0x8C) == 2800


@pytest.mark.parametrize('change', ['owner', 'money', 'index', 'list'])
def test_layout_guard_prevents_all_effect_writes(tmp_path, change):
    game, _, inv, adapter = setup(tmp_path, CASH_ITEM_ID, POWER_TRAP_ID)
    address = {'owner': game.player + 0x90, 'money': game.player + 0x34,
               'index': game.player + 0x3C, 'list': game.players + 0x18}[change]
    game.values[address] = 0xDEADBEEF
    with pytest.raises(MemoryReadError):
        adapter.apply(inv)
    assert not game.writes


def test_default_starting_cash_zero_audio_index_allows_both_effects(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID, POWER_TRAP_ID)
    # Actual Steam Player::init copies this field from the default Money object
    # after assigning the local player index. It legitimately becomes zero.
    game.values[game.player + 0x3C] = 0
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == 25000
    assert game.pointer(game.player + 0x8C) == 1200
    assert progress.effect_receipts == {0, 1}
    load(game, adapter, inv)
    assert game.pointer(game.player + 0x38) == 25000


def test_layout_rejection_names_field_and_keeps_effects_pending(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID, POWER_TRAP_ID)
    game.values[game.player + 0x3C] = 2
    with pytest.raises(MemoryReadError, match='Money audio player index: read 0x2'):
        adapter.apply(inv)
    assert not game.writes and not progress.effect_receipts
    game.values[game.player + 0x3C] = 0
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == 25000
    assert game.pointer(game.player + 0x8C) == 1200


@pytest.mark.parametrize('mode', range(1, 7))
def test_no_effects_in_other_game_modes(tmp_path, mode):
    game, _, inv, adapter = setup(tmp_path, CASH_ITEM_ID, POWER_TRAP_ID)
    game.values[game.logic + 0x94] = mode
    adapter.apply(inv)
    assert not game.writes


def test_story_and_challenge_supported_but_custom_maps_rejected(tmp_path):
    from zh.mission_data import CHALLENGE_MISSIONS
    game, _, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    game.state = Snapshot('usa', 'mission01', 'maps/custom.map', False)
    adapter.apply(inv)
    assert not game.writes
    mission = CHALLENGE_MISSIONS[0]
    game.state = Snapshot(mission['campaign'], mission['mission'], mission['map'], False)
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == 25000


def test_failed_write_is_reserved_and_never_replayed(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    original = game.replace_pointer
    def fail(*args):
        raise MemoryReadError('simulated failure')
    game.replace_pointer = fail
    with pytest.raises(MemoryReadError, match='reserved'):
        adapter.apply(inv)
    assert Progress(tmp_path, 'effects', 0, 1).effect_receipts == {0}
    game.replace_pointer = original
    adapter.apply(inv)
    assert not game.writes


def test_ledger_survives_other_progress_writes(tmp_path):
    _, progress, inv, _ = setup(tmp_path, CASH_ITEM_ID)
    progress.reserve_effects([0])
    progress.mark(min(progress.location_ids))
    progress.record_inventory(inventory(CASH_ITEM_ID, POWER_TRAP_ID).items)
    assert Progress(tmp_path, 'effects', 0, 1).effect_receipts == {0}


def test_new_cash_midmission_only_awards_new_tier(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    adapter.apply(inv)
    expanded = inventory(CASH_ITEM_ID, CASH_ITEM_ID)
    progress.record_inventory(expanded.items)
    adapter.apply(expanded)
    assert game.pointer(game.player + 0x38) == 30000
    load(game, adapter, expanded)
    assert game.pointer(game.player + 0x38) == 30000


def test_mission_transition_before_write_preserves_receipt(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID, POWER_TRAP_ID)
    original = adapter.snapshot
    def transition():
        state = original()
        game.flags = b'\1\0'
        return state
    adapter.snapshot = transition
    with pytest.raises(MemoryReadError, match='Mission changed'):
        adapter.apply(inv)
    assert not progress.effect_receipts and not game.writes


@pytest.mark.parametrize('base_cash', [30000, 18000, 10000])
def test_china_intro_set_money_happens_before_nine_tier_bonus(tmp_path, base_cash):
    game, progress, inv, adapter = setup(tmp_path, *([CASH_ITEM_ID] * 9))
    progress.reserve_effects(range(9))  # unlocks already received in earlier missions
    game.state = Snapshot('china', 'mission01', 'maps/md_chi01/md_chi01.map', False)
    game.input = b'\0'
    load(game, adapter, inv)
    for frame in [120, 300, 900, 1800]:
        game.values[game.logic + 0x3C] = frame
        adapter.apply(inv)
    assert not game.writes and adapter.start_pending and adapter.cash_waiting
    # Actual China1 PLAYER_SET_MONEY scripts, conditioned on INTRO_DONE.
    game.values[game.player + 0x38] = base_cash
    game.input = b'\1'
    adapter.apply(inv)
    game.values[game.logic + 0x3C] = 1830
    messages = adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == base_cash + 45000
    assert any('Mission starting cash: +$45,000' in line for line in messages)
    assert not adapter.start_pending and not adapter.cash_waiting
    adapter.apply(inv)
    assert len(game.writes) == 1
    # Spending and a later cinematic must not re-grant or maintain a balance floor.
    game.values[game.player + 0x38] -= 1000
    game.input = b'\0'; adapter.apply(inv)
    game.input = b'\1'; game.values[game.logic + 0x3C] = 2000
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == base_cash + 44000


def test_cash_and_power_received_in_intro_wait_for_player_control(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID, POWER_TRAP_ID)
    game.input = b'\0'
    adapter.apply(inv)
    assert not progress.effect_receipts
    assert game.pointer(game.player + 0x38) == 20000
    assert game.pointer(game.player + 0x8C) == 0
    assert adapter.cash_waiting
    game.input = b'\1'
    adapter.apply(inv)
    assert progress.effect_receipts == {1}
    game.values[game.logic + 0x3C] += 30
    adapter.apply(inv)
    assert progress.effect_receipts == {0, 1}
    assert game.pointer(game.player + 0x38) == 25000


def test_intro_cash_wait_resets_if_control_is_removed_again(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    game.input = b'\0'; load(game, adapter, inv)
    game.input = b'\1'; adapter.apply(inv)
    game.values[game.logic + 0x3C] += 20
    game.input = b'\0'; adapter.apply(inv)
    game.values[game.logic + 0x3C] += 20
    game.input = b'\1'; adapter.apply(inv)
    assert not progress.effect_receipts
    game.values[game.logic + 0x3C] += 30
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == 25000


def test_saved_game_load_cancels_unawarded_intro_start_bonus(tmp_path):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    progress.reserve_effects([0])
    game.input = b'\0'; load(game, adapter, inv)
    assert adapter.start_pending
    game.input = b'\1'; load(game, adapter, inv, saved=True)
    game.values[game.logic + 0x3C] = 600
    adapter.apply(inv)
    assert game.pointer(game.player + 0x38) == 20000 and not game.writes


@pytest.mark.parametrize('change', ['vtable', 'flag'])
def test_unknown_input_layout_keeps_cash_pending(tmp_path, change):
    game, progress, inv, adapter = setup(tmp_path, CASH_ITEM_ID)
    if change == 'vtable':
        game.values[game.ui] = 0
    else:
        game.input = b'\x02'
    with pytest.raises(MemoryReadError, match='control'):
        adapter.apply(inv)
    assert not progress.effect_receipts and not game.writes
