import asyncio
from types import SimpleNamespace
from dataclasses import replace

import pytest
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

from zh.quickreset import (QuickReset, GAME_STATE_RVA, SAVE_RVA, LOAD_RVA,
                          STRING_CTOR_RVA, UI_RVA, UI_TABLE_RVA)
from zh.deathlink import build_restart_stub, RESTART_RVA
from zh.power import BROWNOUT_RVA
from zh.mission_data import CASH_ITEM_ID
from zh.client import ZeroHourClient, IncompatibleRoom
from test_deathlink import RestartSimulation, state, death_packet
from test_client import Socket
from test_effects import Game, inventory


class CheckpointSimulation(RestartSimulation):
    ui, game_state = 0x2207000, 0x2208000

    def __init__(self, action):
        super().__init__()
        stub = build_restart_stub(self.base, self.code, self.mailbox, quick=True)
        assert len(stub) < 4096
        self.uc.mem_write(self.code, stub)
        self.put(self.mailbox + 12, action)
        self.put(self.base + UI_RVA, self.ui)
        self.put(self.ui, self.base + UI_TABLE_RVA)
        self.uc.mem_write(self.ui + 13, b'\1')
        self.put(self.base + GAME_STATE_RVA, self.game_state)
        self.put(self.player + 0x34, self.base + 0x5456F0)
        self.put(self.player + 0x38, 35000)
        self.put(self.player + 0x8C, 2000)
        self.put(self.mailbox + 28, 10000)
        self.uc.mem_write(self.mailbox + 32, b'AP-QuickReset-test.sav\0')
        for rva, code in ((SAVE_RVA, b'\xc2\x10\0'), (LOAD_RVA, b'\xc2\x3c\0'),
                          (STRING_CTOR_RVA, b'\xc2\x04\0')):
            self.uc.mem_write(self.base + rva, code)
        self.result = 0

    def observe(self, uc, address, size, user_data):
        esp = uc.reg_read(UC_X86_REG_ESP)
        if address == self.base + STRING_CTOR_RVA:
            assert self.get(esp + 4) == self.mailbox + 32
            assert uc.reg_read(UC_X86_REG_ECX) == esp + 8
            self.put(esp + 8, 0x123456)  # simulated managed string allocation
            self.calls.append('string')
        elif address in (self.base + SAVE_RVA, self.base + LOAD_RVA):
            assert uc.reg_read(UC_X86_REG_ECX) == self.game_state
            assert self.get(esp + 4) == 0x123456
            count = 4 if address == self.base + SAVE_RVA else 15
            assert all(self.get(esp + 4 + i*4) == 0 for i in range(1, count))
            self.calls.append('save' if count == 4 else 'load')
            uc.reg_write(UC_X86_REG_EAX, self.result)
        elif address == self.base + BROWNOUT_RVA:
            assert uc.reg_read(UC_X86_REG_ECX) == self.player
            self.calls.append(('brownout', self.get(esp + 4)))
        else:
            super().observe(uc, address, size, user_data)


def test_save_constructs_owned_filename_and_balances_native_arguments():
    g = CheckpointSimulation(1)
    g.run(); g.run()
    assert g.calls == ['string', 'save']
    assert g.get(g.mailbox) == 2
    assert g.get(g.player + 0x38) == 35000  # save must not reconcile anything


@pytest.mark.parametrize('production,low', [(20, 0), (5, 1)])
def test_load_reconciles_new_cash_and_natural_power(production, low):
    g = CheckpointSimulation(2)
    g.put(g.player + 0x84, production)
    g.run(); g.run()
    assert g.calls == ['string', 'load', ('brownout', low)]
    assert g.get(g.player + 0x38) == 45000
    assert g.get(g.player + 0x8C) == 0
    assert g.get(g.mailbox) == 2


@pytest.mark.parametrize('action', [1, 2])
def test_native_error_never_claims_checkpoint_success(action):
    g = CheckpointSimulation(action); g.result = 3; g.run()
    assert g.get(g.mailbox) == 5
    assert g.get(g.mailbox + 24) == 3
    assert g.get(g.player + 0x38) == 35000


def test_input_disabled_rejects_save_but_allows_received_reset():
    for action in [1, 2]:
        g = CheckpointSimulation(action)
        g.uc.mem_write(g.ui + 13, b'\0'); g.run()
        assert g.get(g.mailbox) == (3 if action == 1 else 2)


def test_quick_hook_retains_full_restart_fallback():
    g = CheckpointSimulation(0); g.run()
    assert g.calls == [g.base + RESTART_RVA]


@pytest.mark.parametrize('change', ['money', 'owner', 'overflow'])
def test_loaded_cash_layout_errors_do_not_write(change):
    g = CheckpointSimulation(2)
    address, value = {'money': (g.player + 0x34, 0), 'owner': (g.player + 0x90, 0),
                      'overflow': (g.player + 0x38, 0xFFFFFFFF)}[change]
    g.put(address, value); before = g.get(g.player + 0x38); g.run()
    assert g.get(g.mailbox) == 6 and g.get(g.player + 0x38) == before


def controller(monkeypatch):
    game = Game()
    reset = QuickReset(game)
    game.current = state(frame=60)
    monkeypatch.setattr('zh.quickreset.mission_state', lambda _: game.current)
    monkeypatch.setattr(reset, 'input_enabled', lambda: game.enabled)
    game.enabled = False
    queued = []
    monkeypatch.setattr(reset, '_queue', lambda st, action, bonus=0: queued.append((st, action, bonus)) or True)
    return game, reset, queued, SimpleNamespace(effect_receipts=set())


def test_capture_after_fresh_intro_once_and_never_at_late_attach(monkeypatch):
    game, reset, queued, progress = controller(monkeypatch)
    inv = inventory()
    reset.observe(inv, progress)
    game.current = state(frame=400); reset.observe(inv, progress)
    assert not queued
    game.enabled = True; reset.observe(inv, progress)
    game.current = state(frame=430); reset.observe(inv, progress)
    assert queued[-1][1] == 1
    reset.observe(inv, progress); assert len(queued) == 1
    late = QuickReset(game)
    monkeypatch.setattr(late, 'input_enabled', lambda: True)
    late.observe(inv, progress)
    assert not late.eligible


def test_manual_saved_load_does_not_replace_checkpoint(monkeypatch):
    game, reset, queued, progress = controller(monkeypatch)
    reset.checkpoint = reset.key(game.current)
    game.flags = b'\1\1'; reset.observe(inventory(), progress)
    game.flags = b'\0\0'; game.enabled = True
    reset.observe(inventory(), progress)
    game.current = state(frame=100); reset.observe(inventory(), progress)
    assert not reset.checkpoint and not queued


def test_request_adds_only_cash_not_already_saved(monkeypatch):
    game, reset, queued, progress = controller(monkeypatch)
    inv = inventory(CASH_ITEM_ID, CASH_ITEM_ID, CASH_ITEM_ID, CASH_ITEM_ID)
    progress.effect_receipts = {0, 1, 2}  # fourth item still pending
    reset.checkpoint = reset.key(game.current); reset.captured_tiers = 1
    assert reset.request(game.current, inv, progress)
    assert queued[-1][1:] == (2, 10000)
    reset.checkpoint = None
    reset.request(game.current, inv, progress)
    assert queued[-1][1:] == (0, 0)


def test_successful_restore_retains_checkpoint_with_new_engine_pointers(monkeypatch):
    game, reset, queued, progress = controller(monkeypatch)
    reset.awaiting_load = True
    reset.checkpoint = reset.key(game.current)
    game.current = replace(game.current, mission=0x88888)
    reset.observe(inventory(), progress)
    assert reset.checkpoint == reset.key(game.current) and not reset.awaiting_load
    reset.observe(inventory(), progress)
    assert reset.checkpoint and not queued


def test_checkpoint_waits_for_cash_grant_before_capturing_tiers(monkeypatch):
    game, reset, queued, progress = controller(monkeypatch)
    game.enabled = True
    inv = inventory(CASH_ITEM_ID)
    reset.observe(inv, progress, effects_ready=False)
    game.current = state(frame=300)
    reset.observe(inv, progress, effects_ready=False)
    assert not queued
    progress.effect_receipts.add(0)  # cash was actually applied by effects adapter
    reset.observe(inv, progress, effects_ready=True)
    game.current = state(frame=330)
    reset.observe(inv, progress, effects_ready=True)
    assert queued[-1][1] == 1 and reset.pending_tiers == 1


def test_disabled_capture_tracks_transitions_without_mid_mission_checkpoint(monkeypatch):
    game, reset, queued, progress = controller(monkeypatch)
    game.enabled = True
    reset.observe(inventory(), progress, capture_enabled=False)
    reset.checkpoint = reset.key(game.current)
    game.current = state(frame=400)
    reset.observe(inventory(), progress, capture_enabled=False)
    assert reset.checkpoint  # Existing checkpoint in this mission remains usable.
    game.current = replace(game.current, mission=0x88888)
    reset.observe(inventory(), progress, capture_enabled=False)
    assert not reset.checkpoint
    reset.observe(inventory(), progress, capture_enabled=True)
    game.current = replace(game.current, frame=430)
    reset.observe(inventory(), progress, capture_enabled=True)
    assert not queued and not reset.eligible


@pytest.mark.parametrize('mode', ['full_restart', 'quick_reset', 'bad', None, 1])
def test_protocol_seven_requires_valid_restart_mode(tmp_path, mode):
    async def run():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {'cmd': 'RoomInfo', 'seed_name': 'quick'})
        packet = death_packet()
        packet['slot_data'].update(protocol_version=7, death_link_mode=mode)
        if mode not in ('full_restart', 'quick_reset'):
            with pytest.raises(IncompatibleRoom, match='restart mode'):
                await client.handle(socket, packet)
        else:
            await client.handle(socket, packet)
            assert client.death_link_mode == mode and client.death_link
    asyncio.run(run())
