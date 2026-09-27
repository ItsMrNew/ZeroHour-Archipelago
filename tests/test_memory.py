import struct

import pytest

from zh.memory import CAMPAIGN_GLOBAL_RVA, CAMPAIGN_VTABLE_RVA, GameMemory, MemoryReadError, windows_error


class Image(GameMemory):
    def __init__(self):
        self.base = 0x400000
        self.manager = 0x20000
        self.bytes = {}
        self.put(self.base + CAMPAIGN_GLOBAL_RVA, struct.pack("<I", self.manager))
        self.put(self.manager, struct.pack("<I", self.base + CAMPAIGN_VTABLE_RVA))
        self.put(self.manager + 8, struct.pack("<IIB", 0x30000, 0x40000, 0))
        for field, address, value in [(0x30004, 0x50000, b"USA"),
                                      (0x40004, 0x60000, b"Mission01"),
                                      (0x40008, 0x70000, b"Maps\\MD_USA01\\MD_USA01.map")]:
            self.put(field, struct.pack("<I", address))
            self.put(address, struct.pack("<HH", 1, len(value) + 1) + value + b"\0")

    def put(self, address, data):
        self.bytes.update({address + i: byte for i, byte in enumerate(data)})

    def read(self, address, size):
        return bytes(self.bytes[address + i] for i in range(size))


def test_supported_layout_decodes_stock_mission():
    snapshot = Image().snapshot()
    assert snapshot.campaign == "usa"
    assert snapshot.mission == "mission01"
    assert snapshot.map_name == "maps/md_usa01/md_usa01.map"
    assert snapshot.victorious is False


def test_mismatched_layout_and_invalid_flags_fail_closed():
    image = Image()
    image.put(image.manager, struct.pack("<I", 0xBAD))
    with pytest.raises(MemoryReadError):
        image.snapshot()
    image = Image()
    image.put(image.manager + 16, b"\x02")
    with pytest.raises(MemoryReadError):
        image.snapshot()


def test_incoherent_transition_is_not_a_snapshot():
    image = Image()
    original = image.read
    calls = 0
    def read(address, size):
        nonlocal calls
        if address == image.manager + 8:
            calls += 1
            if calls == 2:
                return struct.pack("<IIB", 0x30000, 0x40000, 1)
        return original(address, size)
    image.read = read
    assert image.snapshot() is None


def test_access_denied_tells_user_how_to_read_elevated_game():
    message = str(windows_error("inspect", 123, 5))
    assert "Run as administrator" in message
    assert "Access denied" in message
    assert "123" in message
    assert "Windows error 299" in str(windows_error("inspect", 123, 299))
