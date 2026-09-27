import os
import struct
from pathlib import Path

import pytest

from zh.compatibility import NativeBase, image, resolve, signature_bytes, validate_executable
from zh.compatibility_data import ANCHORS


def test_native_base_translates_only_verified_addresses():
    base = NativeBase(0x400000, {0x12340: 0x12880, 0x45670: 0x46230})
    assert base + 0x12340 == 0x412880
    assert 0x446230 - base == 0x45670
    with pytest.raises(ValueError, match='Unverified'):
        _ = base + 0x12341
    assert signature_bytes(base, bytes.fromhex('b840234100')) == bytes.fromhex('b880284100')
    assert signature_bytes(0x400000, b'unchanged') == b'unchanged'


@pytest.mark.parametrize('data', [b'', b'wrong game', b'MZ'+b'\0'*100])
def test_non_engine_files_are_rejected(data):
    with pytest.raises(ValueError):
        resolve(data)


def test_installed_update_and_baseline_native_callbacks():
    path = os.environ.get('ZERO_HOUR_TEST_EXE')
    if not path:
        pytest.skip('Set ZERO_HOUR_TEST_EXE for installed-binary validation')
    from zh.power import PowerOutage, TABLE_LAYOUTS
    from zh.deathlink import MissionRestart, CLIENT_TABLE_RVA, CLIENT_TABLE
    from zh.quickreset import QuickReset
    from zh.missiongate import MissionControl
    from zh.unlock_menu import UnlockMenu, TABLE_RVA, TABLE, SIGNATURES
    from zh.consumables import CombatEffects, NATIVE_SIGNATURES
    from zh.reinforcements import SIGNATURES as REINFORCEMENT_SIGNATURES
    from zh.sell_building import SIGNATURES as SELL_SIGNATURES
    for file in (Path(path), Path(path).with_name('Game.dat.bak')):
        if not file.is_file():
            continue
        raw = file.read_bytes()
        addresses, digest = validate_executable(file)
        assert len(addresses) == len(ANCHORS)
        # Changing metadata/overlay changes SHA, not the game ABI.
        assert resolve(raw + b'Harmless overlay with a different file SHA') == addresses
        mapped, base = image(raw)
        class NativeImage:
            def read(self, address, size):
                rva = address-int(self.base)
                return mapped[rva:rva+size]
            def pointer(self, address):
                return struct.unpack('<I', self.read(address,4))[0]
        game = NativeImage()
        game.base = NativeBase(base, addresses)
        for table, layout in {**TABLE_LAYOUTS, CLIENT_TABLE_RVA: CLIENT_TABLE, TABLE_RVA: TABLE}.items():
            assert game.read(game.base+table,len(layout)*4) == struct.pack('<'+'I'*len(layout),*(game.base+r for r in layout))
        for cls in (PowerOutage, MissionRestart, QuickReset, MissionControl, UnlockMenu, CombatEffects):
            adapter = object.__new__(cls)
            adapter.game = game
            if cls is CombatEffects:
                adapter.generals = True
                assert adapter.extra_pages(0x20000000, 0x20008000)
            assert adapter.make_stub(0x20000000, 0x20008000)
        from zh.generals_points import SIGNATURES as GENERALS_SIGNATURES
        for rva, text in (*NATIVE_SIGNATURES, *REINFORCEMENT_SIGNATURES, *SELL_SIGNATURES, *SIGNATURES.items(), *GENERALS_SIGNATURES):
            prefix = bytes.fromhex(text)
            assert game.read(game.base+rva, len(prefix)) == signature_bytes(game.base,prefix,rva)
        from zh.ability_native import DELIVER_VTABLE, CHUTE_VTABLE, CHUTE_DESTINATION
        deliver = game.pointer(game.base+DELIVER_VTABLE+16)
        assert game.read(deliver,6) == bytes.fromhex('8b5424148b01')
        assert game.pointer(game.base+CHUTE_VTABLE+0x90) == game.base+CHUTE_DESTINATION
        # A real opcode/layout change must not be silently accepted.
        pe = struct.unpack_from('<I',raw,60)[0]
        table = pe+24+struct.unpack_from('<H',raw,pe+20)[0]
        text_rva, _, text_offset = struct.unpack_from('<3I',raw,table+12)
        changed = bytearray(raw)
        changed[text_offset+addresses[0x56C60]-text_rva] ^= 1
        with pytest.raises(ValueError):
            resolve(bytes(changed))
