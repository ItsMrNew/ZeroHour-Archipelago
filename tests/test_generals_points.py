"""Run the real reconciliation callback, including native call/stack boundaries."""
import struct

import pytest
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX

from test_power import Simulation
from zh.power import build_stub
from zh.generals_points import (build_points_stub, rank_for_points, SET_RANK,
    POINTS_CHANGED, CONTROL_BAR, ENABLED, PLAYER, CAMPAIGN, MISSION, FRAME,
    BUDGET, RANK_IDS, SCIENCES, RANK, POINTS, SPENT, XP_MODIFIER)
from zh.gameplay import INPUT_OFFSET


class PointsSimulation(Simulation):
    def __init__(self, budget=7, spent=0, rank=1, cap=5):
        super().__init__()
        self.instruction_budget = 3000
        self.uc.mem_map(self.code + 0x3000, 0x1000)
        self.uc.mem_write(self.code, build_stub(self.base, self.code, self.mailbox, generals=True))
        self.uc.mem_write(self.code + 0x3000, build_points_stub(self.base, self.mailbox))
        for rva in (SET_RANK, POINTS_CHANGED):
            self.uc.mem_write(self.base + rva, b'\xc2\x04\x00')
        self.set_calls, self.ui_calls = [], []
        self.vector = self.logic + 0x6000
        for address, value in {
            self.mailbox: 0, self.mailbox + ENABLED: 1,
            self.mailbox + PLAYER: self.player, self.mailbox + CAMPAIGN: self.campaign,
            self.mailbox + MISSION: self.mission, self.mailbox + FRAME: 300,
            self.mailbox + BUDGET: budget, self.logic + 0x98: cap,
            self.base + CONTROL_BAR: self.logic + 0x7000,
            self.player + SCIENCES: self.vector,
            self.player + SCIENCES + 4: self.vector + 12,
            self.player + SCIENCES + 8: self.vector + 128,
            self.player + RANK: rank, self.player + POINTS: 77,
            self.player + SPENT: spent, self.player + XP_MODIFIER: 0x3f800000,
            self.vector: 10, self.vector + 4: 99, self.vector + 8: 100,
        }.items(): self.put(address, value)
        for i in range(5): self.put(self.mailbox + RANK_IDS + i*4, 10+i)

    def observe(self, uc, address, size, user_data):
        super().observe(uc, address, size, user_data)
        if address not in (self.base + SET_RANK, self.base + POINTS_CHANGED): return
        argument = self.get(uc.reg_read(UC_X86_REG_ESP) + 4)
        if address == self.base + SET_RANK:
            assert uc.reg_read(UC_X86_REG_ECX) == self.player
            assert self.get(self.player + RANK) == 0  # never native destructive downgrade
            self.set_calls.append(argument)
            end = self.get(self.player + SCIENCES + 4)
            for i in range(argument): self.put(end + i*4, 10+i)
            self.put(self.player + SCIENCES + 4, end + argument*4)
            self.put(self.player + RANK, argument)
            self.put(self.player + POINTS, self.get(self.player + POINTS) + argument)
        else:
            assert uc.reg_read(UC_X86_REG_ECX) == self.logic + 0x7000
            assert argument == self.player
            self.ui_calls.append(self.get(self.player + POINTS))
        for reg in (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX):
            uc.reg_write(reg, 0xDEADBEEF)

    def sciences(self):
        return [self.get(p) for p in range(self.vector, self.get(self.player + SCIENCES + 4), 4)]


@pytest.mark.parametrize('cap', [5,1000])
@pytest.mark.parametrize('budget,rank', [(0,1),(1,1),(2,2),(3,3),(4,4),(5,4),(6,4),(7,5),(18,5),(28,5)])
def test_received_total_sets_budget_and_rank_and_disables_general_xp(budget, rank, cap):
    game = PointsSimulation(budget, cap=cap)
    game.run()
    assert rank_for_points(budget) == rank
    assert game.get(game.player + RANK) == rank
    assert game.get(game.player + POINTS) == budget
    assert game.get(game.player + XP_MODIFIER) == 0
    assert {99,100} <= set(game.sciences())  # purchased and free mission powers
    assert game.get(game.player + SPENT) == 0
    calls = len(game.ui_calls)
    game.run()
    assert len(game.ui_calls) == calls  # no repeat grants or refresh storm


def test_fresh_challenge_five_starting_points_purchases_and_saved_game():
    game = PointsSimulation(budget=5, cap=1000)
    game.put(game.player + POINTS,1)  # untouched stock challenge opening
    game.run()
    assert game.get(game.player + POINTS) == 5
    assert game.get(game.player + RANK) == 4
    game.put(game.player + SPENT,2)
    game.put(game.player + POINTS,3)
    game.run()
    assert game.get(game.player + POINTS) == 3
    game.put(game.mailbox + BUDGET,6)
    game.run()
    assert game.get(game.player + POINTS) == 4
    # Loading an existing save keeps its purchases; a fresh mission resets them.
    game.put(game.player + POINTS,1)
    game.run()
    assert game.get(game.player + POINTS) == 4
    game.put(game.player + SPENT,0)
    game.run()
    assert game.get(game.player + POINTS) == 6


def test_purchase_new_item_and_checkpoint_restore_use_saved_spending_counter():
    game = PointsSimulation(7, 3)
    game.run()
    assert game.get(game.player + POINTS) == 4
    game.put(game.player + SPENT, 4)  # buy another power
    game.put(game.player + POINTS, 3)
    game.run()
    assert game.get(game.player + POINTS) == 3
    assert game.get(game.player + RANK) == 5  # spending never lowers rank
    game.put(game.mailbox + BUDGET, 8)  # item received mid-mission
    game.run()
    assert game.get(game.player + POINTS) == 4
    game.put(game.player + SPENT, 0)  # a fresh mission or pre-purchase checkpoint
    game.run()
    assert game.get(game.player + POINTS) == 8


def test_rank_downgrade_retains_purchases_and_script_grants_and_respects_mission_cap():
    game = PointsSimulation(2, 4, rank=5)
    for i in range(5): game.put(game.vector + 12 + i*4, 10+i)
    game.put(game.player + SCIENCES + 4, game.vector + 32)
    game.run()
    assert game.sciences() == [99,100,10,11]
    assert game.get(game.player + POINTS) == 0
    game.put(game.mailbox + BUDGET, 28)
    game.put(game.logic + 0x98, 3)
    game.run()
    assert game.get(game.player + RANK) == 3
    assert game.sciences() == [99,100,10,11,12]
    assert game.get(game.player + POINTS) == 24


@pytest.mark.parametrize('change', ['disabled','loading','save','rewound','mission','player','cinematic','bad_cap','bad_spent','bad_vector'])
def test_transition_cutscene_and_layout_guards_prevent_writes(change):
    game = PointsSimulation()
    changes = {
        'disabled': (game.mailbox + ENABLED, 0),
        'loading': (game.logic + 0x51, 1), 'save': (game.logic + 0x52, 1),
        'rewound': (game.logic + 0x3C, 20), 'mission': (game.manager + 12, 0),
        'player': (game.players + 12, 0), 'cinematic': (0x220D000 + INPUT_OFFSET, 0),
        'bad_cap': (game.logic + 0x98, 6), 'bad_spent': (game.player + SPENT, 0xffffffff),
        'bad_vector': (game.player + SCIENCES + 4, game.vector + 1),
    }
    game.put(*changes[change]); game.run()
    assert not game.set_calls and not game.ui_calls
    assert game.get(game.player + POINTS) == 77
    assert game.get(game.player + XP_MODIFIER) == 0x3f800000


def test_installed_stock_largest_promotion_menu_costs_eighteen():
    import os
    import re
    from pathlib import Path
    from stock_ini import read_ini, blocks, field
    from zh.mission_data import GENERALS_POINTS_MAX, GENERALS_POINTS_LIMIT
    path = os.environ.get('ZERO_HOUR_TEST_EXE')
    if not path: pytest.skip('Set ZERO_HOUR_TEST_EXE to audit stock powers')
    folder = Path(path).parent
    sets = blocks(read_ini(folder, 'data/ini/commandset.ini'), 'CommandSet')
    buttons = blocks(read_ini(folder, 'data/ini/commandbutton.ini'), 'CommandButton')
    sciences = blocks(read_ini(folder, 'data/ini/science.ini'), 'Science')
    menus = {}
    for name, body in sets.items():
        if '_CommandSetRank' not in name: continue
        key = name.split('_CommandSetRank')[0]
        for button in re.findall(r'^\s*\d+\s*=\s*(\w+)', body, re.M):
            science = field(buttons.get(button, ''), 'Science')
            if science: menus.setdefault(key, set()).update(science.split())
    costs = {name: sum(int(field(sciences.get(s, ''), 'SciencePurchasePointCost') or 0)
                      for s in ids) for name, ids in menus.items()}
    assert max(costs.values()) == GENERALS_POINTS_MAX == 18
    assert costs['SCIENCE_CHINA'] == costs['Infa_SCIENCE_CHINA'] == 18
    assert GENERALS_POINTS_LIMIT == 28


def test_point_page_is_executable_and_shared_with_existing_effect_hook():
    from types import SimpleNamespace
    from test_power import InstallGame
    from zh.consumables import CombatEffects, NATIVE_SIGNATURES
    from zh.reinforcements import SIGNATURES as REINFORCEMENTS
    from zh.sell_building import SIGNATURES as SELL
    from zh.generals_points import SIGNATURES
    game = InstallGame(0x567B98)
    for rva, prefix in (*NATIVE_SIGNATURES, *REINFORCEMENTS, *SELL, *SIGNATURES):
        game.store(game.base + rva, bytes.fromhex(prefix))
    effects = CombatEffects(game, generals=True)
    state = SimpleNamespace(logic=game.logic)
    effects.install(state)
    assert game.allocations == 1
    assert (effects.region + 0x3000, 0x1000, 0x20) in game.protections
    assert game.pointer(effects.mailbox + ENABLED) == 0
    assert game.read(effects.region + 0x3000, 3) == bytes.fromhex('9c60bf')
    effects.install(state)
    assert game.allocations == 1


def test_controller_reads_rank_store_and_restores_xp_on_close():
    from types import SimpleNamespace
    from zh.generals_points import GeneralsPoints, RANK_STORE
    from zh.mission_data import GENERALS_POINT_ID
    sim = PointsSimulation()
    def replace(address, expected, value):
        assert sim.get(address) == expected
        sim.put(address, value)
    game = SimpleNamespace(base=sim.base, pointer=sim.get,
        read=lambda p,n: bytes(sim.uc.mem_read(p,n)), replace_pointer=replace)
    store, entries = sim.logic + 0x8000, sim.logic + 0x8100
    sim.put(sim.base + RANK_STORE, store)
    sim.put(store + 8, entries); sim.put(store + 12, entries + 20)
    for i, xp in enumerate((0,800,1500,2500,5000)):
        entry, science = sim.logic + 0x8200 + 128*i, sim.logic + 0x8600 + 4*i
        sim.put(entries + 4*i, entry)
        for offset, value in ((4,0),(0x10,xp),(0x14,3 if i == 4 else 1),(0x18,science),(0x1c,science+4)):
            sim.put(entry + offset, value)
        sim.put(science, 10+i)
    state = SimpleNamespace(player=sim.player, loading_map=False, loading_save=False,
                            frame=300, mission=('usa','mission01'))
    effects = SimpleNamespace(game=game, check_same=lambda state: None, snapshot=lambda: state,
        power=SimpleNamespace(mailbox=sim.mailbox, install=lambda state: None))
    controller = GeneralsPoints(effects)
    assert controller.rank_ids() == [10,11,12,13,14]
    inventory = SimpleNamespace(count=lambda item: 3 if item == GENERALS_POINT_ID else 0)
    assert '3 total' in controller.apply(state, inventory)[0]
    sim.run()
    assert sim.get(sim.player + POINTS) == 3
    assert sim.get(sim.player + XP_MODIFIER) == 0
    assert not controller.apply(state, inventory)  # no repeated status message
    controller.close()
    assert sim.get(sim.mailbox + ENABLED) == 0
    assert sim.get(sim.player + XP_MODIFIER) == 0x3f800000
