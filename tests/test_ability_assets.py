import hashlib
import os
from pathlib import Path
import re
import struct

import pytest

from zh.ability_assets import (ASSET_PATH, HEADER, PATRIOT_TEMPLATE, SOURCE_PATH,
                               big_entry, ensure_ability_assets, make_patriot_definition)
from zh.memory import MemoryReadError

STOCK = b'''Object AmericaPatriotBattery
  EnergyProduction = -3
  KindOf = PRELOAD STRUCTURE SELECTABLE POWERED IMMOBILE
  Body = ActiveBody ModuleTag_05
    MaxHealth = 1000.0
    InitialHealth = 1000.0
  End
  ArmorSet
    Armor = StructureArmor
  End
End
Object OtherBuilding
  EnergyProduction = 50
End
'''


def archive(path, source=STOCK, name=SOURCE_PATH):
    name = name.replace('/', '\\').encode() + b'\0'
    start = 16 + 8 + len(name)
    path.write_bytes(b'BIGF' + struct.pack('<I', start + len(source)) +
                     struct.pack('>II', 1, start) + struct.pack('>II', start, len(source)) + name + source)


def test_variant_changes_only_name_and_power_fields():
    generated = make_patriot_definition(STOCK)
    first, _, body = generated.partition(b'\n')
    assert first == (HEADER + hashlib.sha256(body).hexdigest()).encode()
    original = STOCK[:STOCK.index(b'Object OtherBuilding')]
    expected = original.replace(b'Object AmericaPatriotBattery', ('Object ' + PATRIOT_TEMPLATE).encode())
    expected = expected.replace(b'EnergyProduction = -3', b'EnergyProduction = 0').replace(b' POWERED', b'')
    assert body == expected  # health, armor, weapons, modules all unchanged
    assert b'MaxHealth = 1000.0' in body and b'InitialHealth = 1000.0' in body


def test_install_is_additive_idempotent_and_preserves_other_files(tmp_path):
    archive(tmp_path / 'INIZH.big')
    stock_before = (tmp_path / 'INIZH.big').read_bytes()
    assert ensure_ability_assets(tmp_path)
    target = tmp_path / ASSET_PATH
    assert target.read_bytes() == make_patriot_definition(STOCK)
    stamp = target.stat().st_mtime_ns
    assert not ensure_ability_assets(tmp_path)
    assert target.stat().st_mtime_ns == stamp
    assert (tmp_path / 'INIZH.big').read_bytes() == stock_before


def test_install_honors_loose_source_then_patch_archive(tmp_path):
    archive(tmp_path / 'INIZH.big')
    patched = STOCK.replace(b'1000.0', b'1200.0')
    archive(tmp_path / 'PatchINI.big', patched)
    assert ensure_ability_assets(tmp_path)
    assert (tmp_path / ASSET_PATH).read_bytes() == make_patriot_definition(patched)
    loose = tmp_path / SOURCE_PATH
    loose.write_bytes(STOCK.replace(b'1000.0', b'1500.0'))
    assert ensure_ability_assets(tmp_path)
    assert b'MaxHealth = 1500.0' in (tmp_path / ASSET_PATH).read_bytes()


@pytest.mark.parametrize('content', [b'user file\n', make_patriot_definition(STOCK) + b'; edited\n'])
def test_install_preserves_existing_user_file(tmp_path, content):
    archive(tmp_path / 'INIZH.big')
    target = tmp_path / ASSET_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    with pytest.raises(MemoryReadError, match='preserved'):
        ensure_ability_assets(tmp_path)
    assert target.read_bytes() == content


@pytest.mark.parametrize('source', [b'', STOCK.replace(b'POWERED ', b''),
                                  STOCK.replace(b'EnergyProduction', b'EnergyUnknown'),
                                  STOCK.replace(b'\nEnd\n', b'\n  End\n')])
def test_unsupported_source_is_rejected_without_game_changes(tmp_path, source):
    archive(tmp_path / 'INIZH.big', source)
    with pytest.raises(MemoryReadError):
        ensure_ability_assets(tmp_path)
    assert not (tmp_path / ASSET_PATH).exists()


def test_installed_steam_variant_has_stock_1000_health_and_identical_combat_definition():
    path = os.environ.get('ZERO_HOUR_TEST_EXE')
    if not path:
        pytest.skip('Set ZERO_HOUR_TEST_EXE to check installed Steam assets')
    source = big_entry(Path(path).parent / 'INIZH.big', SOURCE_PATH)
    body = make_patriot_definition(source).split(b'\n', 1)[1].decode('cp1252')
    assert re.search(r'MaxHealth\s*=\s*1000\.0', body)
    assert re.search(r'InitialHealth\s*=\s*1000\.0', body)
    reconstructed = body.replace('Object ' + PATRIOT_TEMPLATE, 'Object AmericaPatriotBattery')
    reconstructed = re.sub(r'(EnergyProduction\s*=\s*)0', r'\g<1>-3', reconstructed)
    reconstructed = reconstructed.replace('FS_TECHNOLOGY FS_BASE_DEFENSE', 'FS_TECHNOLOGY POWERED FS_BASE_DEFENSE')
    assert reconstructed.strip() in source.decode('cp1252').replace('\r', '')
