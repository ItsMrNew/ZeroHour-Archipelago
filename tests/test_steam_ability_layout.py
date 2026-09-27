"""Optional checks against the installed executable, independent of native mocks."""
import hashlib
import json
import os
from pathlib import Path
import struct

import pytest

from zh.ability_native import DELIVER_VTABLE
from zh.memory import SUPPORTED_SHA256


def test_steam_constructor_installs_the_concrete_paradrop_vtable():
    path = os.environ.get('ZERO_HOUR_TEST_EXE')
    if not path:
        pytest.skip('Set ZERO_HOUR_TEST_EXE to validate the supported Steam executable')
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != SUPPORTED_SHA256:
        # This fixture records instruction offsets in the historical baseline.
        # Updated callbacks and tables are checked in test_compatibility.py.
        backup = Path(path).with_name('Game.dat.bak')
        if not backup.is_file():
            pytest.skip('Historical baseline binary is unavailable')
        data = backup.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SUPPORTED_SHA256
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    sections = struct.unpack_from('<H', data, pe + 6)[0]
    optional_size = struct.unpack_from('<H', data, pe + 20)[0]
    image_base = struct.unpack_from('<I', data, pe + 24 + 28)[0]
    table = pe + 24 + optional_size

    def read(rva, size):
        for i in range(sections):
            offset = table + i * 40
            _, address, raw_size, raw = struct.unpack_from('<4I', data, offset + 8)
            if address <= rva and rva + size <= address + raw_size:
                return data[raw + rva - address:raw + rva - address + size]
        raise AssertionError(f'RVA {rva:#x} is not backed by executable data')

    # Initial base-class assignment is later replaced with the concrete type.
    assert read(0xBAB55, 6) == bytes.fromhex('c706ac849400')
    final_assignment = read(0xBABB5, 6)
    assert final_assignment[:2] == bytes.fromhex('c706')
    concrete_table = struct.unpack_from('<I', final_assignment, 2)[0]
    assert concrete_table == image_base + DELIVER_VTABLE
    assert concrete_table != struct.unpack('<I', read(0xBAB57, 4))[0]
    # The five-argument OCL entry dispatches into the DeliverPayload create method.
    assert struct.unpack('<I', read(DELIVER_VTABLE + 16, 4))[0] == image_base + 0xBAE80
    assert read(0xBAE80, 6) == bytes.fromhex('8b5424148b01')
    # Independent native name tables and parachute consumer confirm enum indices.
    from zh.ability_native import PARACHUTABLE_MASK
    from zh.unlock_menu import PARADROP_CURSOR
    def name_at(table, index):
        pointer = struct.unpack('<I', read(table + index * 4, 4))[0]
        return read(pointer - image_base, 32).split(b'\0')[0]
    assert name_at(0x5E3C4C, 0) == b'OBSTACLE'
    assert name_at(0x5E3C4C, 32 + PARACHUTABLE_MASK.bit_length() - 1) == b'PARACHUTABLE'
    assert name_at(0x5E16B4, PARADROP_CURSOR) == b'PARADROP'
    assert read(0x22BB71, 2) == bytes.fromhex('6a28')  # push KINDOF_PARACHUTABLE (40)
    fixture = json.loads((Path(__file__).parent / 'fixtures/steam_parachute_admission.json').read_text())
    for rva, code in fixture.items():
        assert read(int(rva), len(code) // 2) == bytes.fromhex(code)
    fixture = json.loads((Path(__file__).parent / 'fixtures/steam_airdrop_cargo.json').read_text())
    for rva, code in fixture.items():
        assert read(int(rva), len(code) // 2) == bytes.fromhex(code)
    from zh.ability_native import TRANSPORT_SLOTS, CHUTE_VTABLE, CHUTE_DESTINATION
    assert read(0x146DC2, 7) == bytes.fromhex('0fbeb8') + struct.pack('<I', TRANSPORT_SLOTS)
    assert struct.unpack('<I', read(CHUTE_VTABLE + 0x90, 4))[0] == image_base + CHUTE_DESTINATION
    assert struct.unpack('<I', read(CHUTE_VTABLE + 0x68, 4))[0] == image_base + 0x22BB30
