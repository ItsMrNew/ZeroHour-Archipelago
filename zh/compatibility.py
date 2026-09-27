"""Resolve native addresses by instruction/layout evidence, not a file hash.

The baseline RVAs remain stable identifiers in the adapters. NativeBase translates
each base + RVA at the point a native address is emitted or read. Unknown RVAs
are errors; there is deliberately no guessed offset or unchecked-hash mode.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import re
import struct

from .compatibility_data import ANCHORS, SIGNATURE_OPERANDS


def image(data):
    try:
        if data[:2] != b'MZ':
            raise ValueError('Not a Windows executable.')
        pe = struct.unpack_from('<I', data, 60)[0]
        if data[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H', data, pe+4)[0] != 0x14c:
            raise ValueError('Expected a 32-bit x86 game engine.')
        count, optional = struct.unpack_from('<H', data, pe+6)[0], pe+24
        if struct.unpack_from('<H', data, optional)[0] != 0x10b:
            raise ValueError('Unsupported executable format.')
        base, size = struct.unpack_from('<I', data, optional+28)[0], struct.unpack_from('<I', data, optional+56)[0]
        if base != 0x400000 or not 0 < size <= 32*1024*1024 or not 1 <= count <= 32:
            raise ValueError('Unsupported game image layout.')
        mapped = bytearray(size)
        table = optional + struct.unpack_from('<H', data, pe+20)[0]
        for n in range(count):
            _, rva, length, offset = struct.unpack_from('<4I', data, table+n*40+8)
            if rva+length > size or offset+length > len(data):
                raise ValueError('Invalid executable section.')
            mapped[rva:rva+length] = data[offset:offset+length]
        return bytes(mapped), base
    except (struct.error, IndexError) as error:
        raise ValueError('Incomplete executable headers.') from error


def _matches(raw, mask, data):
    pattern = b''.join(re.escape(bytes([b])) if m else b'.' for b, m in zip(raw, mask))
    return [m.start() for m in re.finditer(pattern, data, re.S)]


def resolve(data):
    mapped, base = image(data)
    addresses = {}
    def address(rva):
        if rva in addresses:
            return addresses[rva]
        recipe = ANCHORS[rva]
        if isinstance(recipe, dict) and 'operand_of' in recipe:
            location = address(recipe['operand_of']) + recipe['offset']
            candidates = [struct.unpack_from('<I', mapped, location)[0]-base]
        elif isinstance(recipe, dict):
            raw, mask = map(bytes.fromhex, recipe['verify'])
            if 'table' in recipe:
                location = address(recipe['table']) + recipe['offset']
                candidates = [struct.unpack_from('<I', mapped, location)[0]-base]
            else:
                candidates = []
                for pos in _matches(raw, mask, mapped):
                    ptr = struct.unpack_from('<I', mapped, pos+recipe['operand'])[0]-base
                    name = recipe['named'].encode() + b'\0'
                    if 0 <= ptr <= len(mapped)-len(name) and mapped[ptr:ptr+len(name)] == name:
                        candidates.append(pos)
            candidates = [p for p in candidates if 0 <= p <= len(mapped)-len(raw)
                          and all(not m or b == mapped[p+i] for i, (b,m) in enumerate(zip(raw,mask)))]
        else:
            candidates = []
            for raw_hex, mask_hex, operand in recipe:
                hits = _matches(bytes.fromhex(raw_hex), bytes.fromhex(mask_hex), mapped)
                if len(hits) != 1:
                    raise ValueError(f'Native layout {rva:#x} has {len(hits)} matching anchors.')
                pos = hits[0]
                if isinstance(operand, list):
                    target = pos + operand[1] + struct.unpack_from('<i', mapped, pos+operand[0])[0]
                elif operand is None:
                    target = pos
                else:
                    target = struct.unpack_from('<I', mapped, pos+operand)[0]-base
                candidates.append(target)
        if not candidates or len(set(candidates)) != 1 or not 0 < candidates[0] < len(mapped):
            raise ValueError(f'Native layout {rva:#x} could not be verified uniquely.')
        addresses[rva] = candidates[0]
        return candidates[0]
    for rva in ANCHORS:
        address(rva)
    return addresses


class NativeBase(int):
    """Image base with checked translation of baseline native RVA identifiers."""
    def __new__(cls, value, addresses):
        result = super().__new__(cls, value)
        result.addresses = addresses
        result.reverse = {v:k for k,v in addresses.items()}
        return result

    def __add__(self, rva):
        if rva not in self.addresses:
            raise ValueError(f'Unverified native address {rva:#x}.')
        return int(self) + self.addresses[rva]

    def __rsub__(self, pointer):
        # The hook adapters identify an original vtable by its baseline RVA.
        return self.reverse.get(pointer-int(self), -1)


def signature_bytes(base, raw, rva=None):
    if not isinstance(base, NativeBase):
        return raw  # Unit-test memory adapters use the baseline integer base.
    result = bytearray(raw)
    if rva is not None:
        for offset, target in SIGNATURE_OPERANDS.get(rva, []):
            size = min(4, len(raw)-offset)
            if size > 0:
                original = struct.pack('<I', 0x400000+target)[:size]
                if raw[offset:offset+size] != original:
                    raise ValueError('Native signature does not match its recorded operands.')
                result[offset:offset+size] = struct.pack('<I', base+target)[:size]
        return bytes(result)
    index = 0
    while index <= len(raw)-4:
        rva = struct.unpack_from('<I', raw, index)[0]-0x400000
        if rva in base.addresses:
            struct.pack_into('<I', result, index, base+rva)
            index += 4
        else:
            index += 1
    return bytes(result)


@lru_cache(maxsize=4)
def _validated(path, size, modified):
    data = Path(path).read_bytes()
    return resolve(data), hashlib.sha256(data).hexdigest()


def validate_executable(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _validated(str(path), stat.st_size, stat.st_mtime_ns)
