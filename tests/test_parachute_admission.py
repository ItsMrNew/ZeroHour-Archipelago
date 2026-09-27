"""Run Steam's actual parachute admission and KindOf code, not a mask mock."""
import json
from pathlib import Path
import struct

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

from zh.ability_native import PARACHUTABLE_MASK


@pytest.mark.parametrize('mask,occupants,expected', [(0, 0, False), (0x800, 0, False),
    (PARACHUTABLE_MASK, 0, True), (PARACHUTABLE_MASK, 1, False)])
def test_steam_parachute_accepts_patriot_only_with_correct_flag(mask, occupants, expected):
    native = json.loads((Path(__file__).parent / 'fixtures/steam_parachute_admission.json').read_text())
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x700000)
    u.mem_map(0x2000000, 0x10000)
    for rva, code in native.items():
        u.mem_write(0x400000 + int(rva), bytes.fromhex(code))
    # OpenContain's allow-mask/owner checks pass for our own parachutable payload.
    # The real subsequent check rejects slotless non-infantry without bit 40.
    u.mem_write(0x621100, bytes.fromhex('b801000000c20800'))
    u.mem_write(0x546DB0, bytes.fromhex('33c0c3'))  # Patriot has zero transport slots
    u.mem_write(0x2005000, b'\xb8' + struct.pack('<I', occupants) + b'\xc3')
    obj, template, container, vtable, stack, stop = (0x2001000, 0x2002000, 0x2003000,
                                                   0x2004000, 0x2007000, 0x2008000)
    for address, value in {obj + 4: template, template + 0x68: 0x80,
                           template + 0x6C: 0x1020 | mask, container: vtable,
                           vtable + 0xA4: 0x2005000}.items():
        u.mem_write(address, struct.pack('<I', value))
    u.mem_write(stack, struct.pack('<3I', stop, obj, 1))
    u.reg_write(UC_X86_REG_ESP, stack)
    u.reg_write(UC_X86_REG_ECX, container)
    u.emu_start(0x62BB30, stop, count=1000)
    assert bool(u.reg_read(UC_X86_REG_EAX) & 0xFF) == expected
    assert u.reg_read(UC_X86_REG_ESP) == stack + 12
