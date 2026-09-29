import struct
from types import SimpleNamespace

import pytest
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP

from test_power import Simulation
from zh import consumables as c, sell_building as s
from zh.power import build_stub
from zh.gameplay import INPUT_OFFSET


class SaleSimulation(Simulation):
    instruction_budget = 20000
    assistant = 0x2209000

    def __init__(self, cases=('valid',), seed=123):
        self.sold = []
        self.removed = []
        self.production_refund = 1250
        self.objects = {}
        super().__init__()
        self.uc.mem_map(0x2300000, 0x10000)
        self.uc.mem_map(self.code + c.boosts.PAGE, 0x1000)
        self.uc.mem_write(self.code + c.boosts.PAGE, c.boosts.page(self.base, self.mailbox))
        self.uc.mem_write(self.code, build_stub(self.base, self.code, self.mailbox, True))
        self.put(self.player + 0x38, 20000)
        self.put(self.mailbox + 28, 5)
        self.put(self.mailbox + s.SEED, seed)
        self.put(self.base + c.ASSISTANT_RVA, self.assistant)
        self.put(self.assistant, self.base + c.ASSISTANT_TABLE_RVA)
        # Actual callback calls with cdecl arguments; native iterator is thiscall.
        iterator = bytearray.fromhex('56 57 8b 74 24 0c 8b 7c 24 10')
        for i, case in enumerate(cases):
            obj = 0x2300000 + i * 0x400
            self.objects[obj] = case
            self.put(obj + 0x64, 100 + i)
            if case in ('dead', 'offmap'):
                self.put(obj + 0x277, 1 if case == 'dead' else 8)
            if case in ('destroyed', 'construction', 'unselectable', 'sold', 'masked'):
                self.put(obj + 0x80, 1 << dict(destroyed=1, construction=3, unselectable=4, sold=19, masked=22)[case])
            if case == 'unsellable': self.put(obj + 0x276, 4)
            iterator += b'\x57\x68' + struct.pack('<I', obj) + bytes.fromhex('ff d6 83 c4 08')
        iterator += bytes.fromhex('5f 5e c2 08 00')
        self.uc.mem_write(self.base + c.ITERATE_RVA, bytes(iterator))
        for rva, count in ((c.KINDOF_RVA, 4), (c.GET_OWNER_RVA, 0), (s.SELL_RVA, 4), (0xA4000, 4)):
            self.uc.mem_write(self.base + rva, bytes((0xC2, count, 0)))

    def observe(self, uc, address, size, user_data):
        super().observe(uc, address, size, user_data)
        this = uc.reg_read(UC_X86_REG_ECX)
        sp = uc.reg_read(UC_X86_REG_ESP)
        result = 0
        if address == self.base + c.KINDOF_RVA:
            assert self.get(sp + 4) == 7
            result = int(self.objects[this] != 'unit')
        elif address == self.base + c.GET_OWNER_RVA:
            result = self.player + (4 if self.objects[this] == 'enemy' else 0)
        elif address == self.base + s.SELL_RVA:
            assert this == self.assistant
            obj = self.get(sp + 4)
            assert self.objects[obj] == 'valid'
            self.sold.append(obj)
            self.put(obj + 0x80, 1 << 19)
            self.put(self.player + 0x38, self.get(self.player + 0x38) + self.production_refund)
        elif address == self.base + 0xA4000:
            assert this == self.logic
            obj = self.get(sp + 4)
            assert obj in self.sold
            self.removed.append(obj)
        else:
            return
        uc.reg_write(UC_X86_REG_EAX, result)
        uc.reg_write(UC_X86_REG_ECX, 0xDEADBEEF)
        uc.reg_write(UC_X86_REG_EDX, 0xDEADBEEF)


def test_sale_filters_targets_and_calls_native_sale_once_with_local_building():
    cases = ('unit', 'enemy', 'dead', 'offmap', 'destroyed', 'construction',
             'unselectable', 'sold', 'masked', 'unsellable', 'valid')
    sim = SaleSimulation(cases)
    sim.run()
    assert sim.sold == [0x2300000 + 10 * 0x400]
    assert sim.get(sim.mailbox) == 2 and sim.get(sim.mailbox + 24) == 110
    sim.run()
    assert len(sim.sold) == 1
    effect = c.CombatEffects(SimpleNamespace(pointer=sim.get))
    effect.mailbox, effect.operation, effect.reported = sim.mailbox, 5, False
    assert 'building #110' in effect.poll()[0]
    assert effect.poll() == []


def test_sale_random_selection_can_choose_every_eligible_building():
    choices = set()
    for seed in range(1, 25):
        sim = SaleSimulation(('valid', 'valid', 'valid'), seed)
        sim.run()
        assert len(sim.sold) == 1
        choices.update(sim.sold)
    assert choices == {0x2300000, 0x2300400, 0x2300800}


@pytest.mark.parametrize('cases', [(), ('unit', 'enemy', 'unsellable', 'sold')])
def test_no_eligible_building_consumes_trap_without_mutation(cases):
    sim = SaleSimulation(cases)
    sim.run()
    assert sim.get(sim.mailbox) == 6 and not sim.sold
    effect = c.CombatEffects(SimpleNamespace(pointer=sim.get))
    effect.mailbox, effect.operation, effect.reported = sim.mailbox, 5, False
    assert 'no eligible building' in effect.poll()[0]


def test_sale_waits_for_control_and_does_not_replay_afterwards():
    sim = SaleSimulation()
    sim.put(0x220D000 + INPUT_OFFSET, 0)
    sim.run()
    assert sim.get(sim.mailbox) == 1 and not sim.sold
    sim.put(sim.logic + 0x3C, 2400)
    sim.put(0x220D000 + INPUT_OFFSET, 1)
    sim.run()
    sim.run()
    assert len(sim.sold) == 1


def test_sale_rejects_mission_transition_while_waiting():
    sim = SaleSimulation()
    sim.put(0x220D000 + INPUT_OFFSET, 0)
    sim.run()
    sim.put(sim.logic + 0x52, 1)
    sim.run()
    assert sim.get(sim.mailbox) == 3 and not sim.sold


def test_next_trap_never_selects_a_building_already_being_sold():
    sim = SaleSimulation(('valid', 'valid'))
    for _ in range(3):
        sim.put(sim.mailbox, 1)
        sim.run()
    assert len(sim.sold) == 2 and len(set(sim.sold)) == 2
    assert sim.get(sim.mailbox) == 6


@pytest.mark.parametrize('no_refund', [False, True])
def test_sale_refund_mode_preserves_or_suppresses_all_sale_cash(no_refund):
    sim = SaleSimulation()
    sim.put(sim.mailbox + s.NO_REFUND, int(no_refund))
    sim.run()
    assert len(sim.sold) == 1
    assert sim.removed == (sim.sold if no_refund else [])
    assert sim.get(sim.player + 0x38) == (20000 if no_refund else 21250)
    # Later income is untouched: no client-side delayed balance subtraction.
    sim.put(sim.player + 0x38, sim.get(sim.player + 0x38) + 600)
    sim.run()
    assert sim.get(sim.player + 0x38) == (20600 if no_refund else 21850)
    assert len(sim.sold) == 1


def test_no_refund_no_target_does_not_touch_cash():
    sim = SaleSimulation(('enemy', 'unsellable'))
    sim.put(sim.mailbox + s.NO_REFUND, 1)
    sim.run()
    assert sim.get(sim.player + 0x38) == 20000
    assert not sim.removed and not sim.sold
