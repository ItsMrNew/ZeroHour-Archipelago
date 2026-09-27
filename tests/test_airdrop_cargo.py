"""Execute the supported Steam cargo gates, including the parachute wrapper."""
import json
from pathlib import Path
import struct

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

from zh.ability_native import PARACHUTABLE_MASK, TRANSPORT_SLOTS


@pytest.mark.parametrize('slots,override', [(0, False), (1, False), (0, True), (1, True)])
def test_native_plane_requires_transport_slot_even_for_parachutable_building(slots, override):
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x700000)
    u.mem_map(0x2000000, 0x10000)
    for filename in ('steam_parachute_admission.json', 'steam_airdrop_cargo.json'):
        fixture = json.loads((Path(__file__).parent / 'fixtures' / filename).read_text())
        for rva, code in fixture.items():
            u.mem_write(0x400000 + int(rva), bytes.fromhex(code))

    def put(addr, value):
        u.mem_write(addr, struct.pack('<I', value))

    def run(addr, this, args):
        stack, stop = 0x200E000, 0x200F000
        u.mem_write(stack, struct.pack('<' + 'I' * (1 + len(args)), stop, *args))
        u.reg_write(UC_X86_REG_ESP, stack)
        u.reg_write(UC_X86_REG_ECX, this)
        u.emu_start(addr, stop, count=2000)
        assert u.reg_read(UC_X86_REG_ESP) == stack + 4 * (1 + len(args))
        return u.reg_read(UC_X86_REG_EAX)

    # Own plane/parachute: stock allow masks accept PARACHUTABLE. Exercise that
    # through the real isKindOf, while owner lookup is a same-player boundary.
    u.mem_write(0x621100, bytes.fromhex('8b4c24046a28e8') +
                struct.pack('<i', 0x544570 - (0x621100 + 11)) + bytes.fromhex('c20800'))
    u.mem_write(0x548290, bytes.fromhex('b801000000c3'))
    u.mem_write(0x2000100, bytes.fromhex('b801000000c3'))
    u.mem_write(0x2000120, bytes.fromhex('b864000000c3'))
    u.mem_write(0x2000140, bytes.fromhex('8d4120c3'))
    u.mem_write(0x2000160, bytes.fromhex('33c0c3'))
    patriot, template, final, chute, contain, plane_contain, vt = (
        0x2001000, 0x2002000, 0x2003000, 0x2004000, 0x2005000, 0x2006000, 0x2007000)
    put(patriot + 4, template)
    if override:
        put(template + 4, final)
    else:
        final = template
    put(final + 0x68, 0x80)  # structure
    put(final + 0x6C, PARACHUTABLE_MASK)
    u.mem_write(final + TRANSPORT_SLOTS, bytes([slots]))
    for addr, value in {chute + 0x170: contain, chute + 4: template,
                        contain: vt, plane_contain: vt,
                        vt + 0x10: 0x2000100, vt + 0x50: 0x2000120,
                        vt + 0xA4: 0x2000160, vt + 0xA8: 0x2000140,
                        contain + 0x20: contain + 0x30,
                        contain + 0x30: contain + 0x40,
                        contain + 0x40: contain + 0x30,
                        contain + 0x48: patriot}.items():
        put(addr, value)
    assert run(0x62BB30, contain, [patriot, 1]) & 0xFF == 1
    # This is the missing gate in 0.15.2: it unwraps the parachute, so simply
    # allowing the parachute to hold the building does NOT load the plane.
    assert bool(run(0x626F70, plane_contain, [chute, 1]) & 0xFF) == bool(slots)
    assert run(0x546DB0, chute, []) == slots


def test_airdrop_rejects_ranger_rider_instead_of_reporting_patriot_success():
    from test_abilities import PatriotSimulation
    from zh import ability_native as a
    sim = PatriotSimulation()
    # A non-Patriot inside the second parachute must fail native verification.
    rider = sim.cargo + 0x2800
    sim.put(rider + 4, sim.template)
    sim.run()
    assert sim.get(sim.mailbox) == 5
    assert sim.get(sim.mailbox + a.DROP_COUNT) == 1
    assert sim.get(sim.patriot + a.TRANSPORT_SLOTS) & 255 == 0


@pytest.mark.parametrize('count', [0, 2, 4, 5])
def test_airdrop_checks_exact_plane_cargo_count(count):
    from test_abilities import PatriotSimulation
    from zh import ability_native as a
    sim = PatriotSimulation()
    sim.uc.mem_write(sim.cargo + 0x300, b'\xb8' + struct.pack('<I', count) + b'\xc3')
    sim.run()
    assert sim.get(sim.mailbox) == 5
    assert sim.get(sim.mailbox + a.DROP_COUNT) == 0


def test_airdrop_patches_final_map_template_and_restores_both_fields():
    from test_abilities import PatriotSimulation
    from zh import ability_native as a
    class OverrideSimulation(PatriotSimulation):
        def observe(self, uc, address, size, data):
            self.patriot = final if address == self.base + a.CREATE_OCL else base_template
            super().observe(uc, address, size, data)
    sim = OverrideSimulation()
    base_template = sim.patriot
    final = base_template + 0x400
    sim.put(base_template + 4, final)
    sim.put(final + 0x68, 0x80)
    sim.put(final + 0x6C, 0x1020)
    # Make the creation assertions use the actual effective template, while
    # factory lookup still returns the base entry with its map override.
    sim.run()
    assert sim.get(sim.mailbox) == 2
    assert sim.get(final + 0x6C) == sim.get(base_template + 0x6C) == 0x1020
    assert sim.get(final + a.TRANSPORT_SLOTS) & 255 == 0
