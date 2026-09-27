"""Generate a distinct, save-compatible Patriot from the user's installed INI.

No stock assets are redistributed or overridden. The engine loads this additive
object definition at startup, so its energy and POWERED properties also remain
correct after capture, sale, destruction, save/load, or a client disconnect.
"""
import hashlib
from pathlib import Path
import re
import struct

from .memory import MemoryReadError

PATRIOT_TEMPLATE = 'AP_PatriotBattery'
ASSET_PATH = Path('Data/INI/Object/ZZArchipelagoPatriot.ini')
SOURCE_PATH = 'Data/INI/Object/FactionBuilding.ini'
HEADER = '; Archipelago generated ability object v1 sha256='


def big_entry(path, wanted):
    data = Path(path).read_bytes()
    if data[:4] not in (b'BIGF', b'BIG4') or len(data) < 16:
        raise ValueError('Invalid BIG archive')
    count = struct.unpack_from('>I', data, 8)[0]
    if count > 100000:
        raise ValueError('Invalid BIG entry count')
    cursor = 16
    for _ in range(count):
        offset, length = struct.unpack_from('>II', data, cursor)
        cursor += 8
        end = data.index(0, cursor)
        name = data[cursor:end].decode('ascii').replace('\\', '/')
        cursor = end + 1
        if name.casefold() == wanted.casefold():
            if offset < cursor or offset + length > len(data):
                raise ValueError('Invalid BIG entry bounds')
            return data[offset:offset + length]
    return None


def make_patriot_definition(source):
    source = source.decode('cp1252').replace('\r', '')
    start = re.search(r'^Object[ \t]+AmericaPatriotBattery[ \t]*(?:;[^\n]*)?$', source, re.M)
    if not start:
        raise ValueError('Standard Patriot definition is missing')
    # Stock definitions have unindented Object/End delimiters; nested module
    # End lines are indented. Reject ambiguous layouts instead of copying more.
    end = re.search(r'^End[ \t]*(?:;[^\n]*)?$', source[start.end():], re.M)
    if not end:
        raise ValueError('Standard Patriot definition is incomplete')
    original = source[start.start():start.end() + end.end()] + '\n'
    if len(re.findall(r'^Object\b', original, re.M)) != 1:
        raise ValueError('Ambiguous Patriot definition')
    energy = re.compile(r'^(\s*EnergyProduction\s*=\s*)-?\d+([^\n]*)$', re.M)
    kinds = re.compile(r'^(\s*KindOf\s*=\s*)([^;\n]+)([^\n]*)$', re.M)
    if len(energy.findall(original)) != 1 or len(kinds.findall(original)) != 1:
        raise ValueError('Unsupported Patriot power fields')
    match = kinds.search(original)
    flags = match[2].split()
    if flags.count('POWERED') != 1 or 'STRUCTURE' not in flags:
        raise ValueError('Unsupported Patriot KindOf flags')
    result = re.sub(r'^Object[ \t]+AmericaPatriotBattery\b', 'Object ' + PATRIOT_TEMPLATE, original, count=1)
    result = energy.sub(lambda m: m[1] + '0' + m[2], result)
    result = kinds.sub(lambda m: m[1] + ' '.join(f for f in flags if f != 'POWERED') + m[3], result)
    body = result.encode('cp1252')
    return (HEADER + hashlib.sha256(body).hexdigest() + '\n').encode('ascii') + body


def ensure_ability_assets(game_dir):
    """Return True after installing/updating our own file; leave user edits alone."""
    root = Path(game_dir).resolve()
    target = root / ASSET_PATH
    if not target.resolve().is_relative_to(root):
        raise MemoryReadError('Ability asset path is outside the game directory.')
    try:
        loose = root / SOURCE_PATH
        source = loose.read_bytes() if loose.is_file() else None
        if source is None and (root / 'PatchINI.big').is_file():
            source = big_entry(root / 'PatchINI.big', SOURCE_PATH)
        if source is None:
            source = big_entry(root / 'INIZH.big', SOURCE_PATH)
        if source is None:
            raise ValueError('FactionBuilding.ini was not found')
        desired = make_patriot_definition(source)
        if target.exists():
            current = target.read_bytes()
            if current == desired:
                return False
            first, separator, body = current.partition(b'\n')
            expected = (HEADER + hashlib.sha256(body).hexdigest()).encode('ascii')
            if not separator or first != expected:
                raise ValueError('Existing ZZArchipelagoPatriot.ini was edited or is not owned by this client; preserved')
        target.parent.mkdir(parents=True, exist_ok=True)
        # Only publish a completely written definition.
        temporary = target.with_suffix('.ini.ap-tmp')
        with temporary.open('xb') as stream:
            stream.write(desired)
        temporary.replace(target)
        return True
    except (OSError, ValueError, struct.error) as exc:
        raise MemoryReadError(f'Could not install the standalone Patriot ability definition: {exc}') from exc
