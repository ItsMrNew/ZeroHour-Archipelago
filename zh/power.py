"""Schedule native brownout on GameLogic's simulation update, never a remote thread.

The instance gets a private copy of its eight-entry vtable. Only update is
redirected. Published pages stay allocated until game exit, so unhooking cannot
free code that an in-flight update is still executing.
"""
import ctypes as ct
from ctypes import wintypes as wt
import struct

from .compatibility import signature_bytes
from .memory import CAMPAIGN_GLOBAL_RVA, MemoryReadError, windows_error
from .dozer import GAME_LOGIC_RVA
from .gameplay import UI_RVA, UI_TABLE_RVA, INPUT_OFFSET

LOGIC_VTABLE_RVA = 0x547808
UPDATE_RVA = 0xA3800
BROWNOUT_RVA = 0x56C60
PLAYER_LIST_RVA = 0x6395A0
ENERGY_VTABLE_RVA = 0x54F758
# Destructor, init, postProcessLoad, reset, update, draw, two factory methods.
VTABLE_RVAS = (0x9ED00, 0x9F1E0, 0x21D640, 0x9F4A0, UPDATE_RVA,
               0x21D640, 0xA47E0, 0xA4780)
TABLE_LAYOUTS = {
    LOGIC_VTABLE_RVA: VTABLE_RVAS,
    # W3DGameLogic changes destructor and the two device object factories.
    0x567B98: (0x3417F0, *VTABLE_RVAS[1:6], 0x341730, 0x341790),
}


def build_stub(base, code, mailbox, extras=False, generals=False):
    """Small x86 thunk. Mailbox: status, player, frame, duration, campaign, mission, end.

    status 0 idle, 1 published, 4 claimed, 2 applied, 3 rejected.
    pushad/pushfd preserve entry registers and flags before tail-calling update.
    The game's thiscall brownout routine pops its single four-byte argument.
    """
    out, labels, branches = bytearray(), {}, []
    def emit(hex_bytes, *words):
        out.extend(bytes.fromhex(hex_bytes))
        for word in words:
            out.extend(struct.pack('<I', word))
    def branch(op, label):
        emit(op)
        branches.append((len(out), label))
        emit('00 00 00 00')
    emit('9c 60 bf', mailbox)                 # pushfd; pushad; mov edi, mailbox
    if generals:
        emit('b8', code + 0x3000); emit('ff d0')
    if extras:
        from .consumables import emit_maintenance
        emit_maintenance(emit, branch, labels, out, base, mailbox)
    emit('83 3f 01')                         # only published requests
    branch('0f 85', 'done')
    emit('b8', 1)
    emit('ba', 4)
    emit('f0 0f b1 17')                      # lock cmpxchg [edi], edx
    branch('0f 85', 'done')
    emit('3b 0d', base + GAME_LOGIC_RVA)      # this == TheGameLogic
    branch('0f 85', 'reject')
    for offset in (0x51, 0x52, 0x64):        # no loading or scheduled new game
        emit(f'80 79 {offset:02x} 00')
        branch('0f 85', 'reject')
    emit('83 b9 94 00 00 00 00')             # stock single player mode
    branch('0f 85', 'reject')
    emit('8b 59 3c 3b 5f 08')                # frame >= request frame
    branch('0f 82', 'reject')
    emit('a1', base + PLAYER_LIST_RVA)
    emit('85 c0')
    branch('0f 84', 'reject')
    emit('8b 70 0c 85 f6')                   # current local player
    branch('0f 84', 'reject')
    emit('3b 77 04')
    branch('0f 85', 'reject')
    emit('81 be 80 00 00 00', base + ENERGY_VTABLE_RVA)
    branch('0f 85', 'reject')
    emit('39 b6 90 00 00 00')                # energy owner == player
    branch('0f 85', 'reject')
    emit('a1', base + CAMPAIGN_GLOBAL_RVA)
    emit('85 c0')
    branch('0f 84', 'reject')
    emit('80 78 10 00')                      # not victory/menu
    branch('0f 85', 'reject')
    emit('8b 50 08 3b 57 10')                # same campaign
    branch('0f 85', 'reject')
    emit('8b 50 0c 3b 57 14')                # same mission
    branch('0f 85', 'reject')
    # A cutscene may begin between the client's control check and this update.
    # Keep the same request pending; do not start a timer or consume it twice.
    emit('a1', base + UI_RVA)
    emit('85 c0'); branch('0f 84', 'defer')
    emit('81 38', base + UI_TABLE_RVA); branch('0f 85', 'reject')
    emit(f'80 78 {INPUT_OFFSET:02x} 01'); branch('0f 85', 'defer')
    if extras:
        from .consumables import emit_dispatch
        emit_dispatch(emit, branch, labels, out, base, code, mailbox)
    emit('8b 86 8c 00 00 00 39 d8 0f 42 c3')  # max(expiry, frame)
    emit('03 47 0c')                         # + duration
    branch('0f 82', 'reject')                # reject unsigned overflow
    emit('89 86 8c 00 00 00 89 47 18')      # store native expiry and result
    emit('89 f1 6a 01')                      # this=player; brownOut=true
    emit('b8', base + BROWNOUT_RVA)
    emit('ff d0')                            # call native routine on game thread
    emit('c7 07', 2)
    branch('e9', 'done')
    labels['defer'] = len(out)
    emit('c7 07', 1)
    branch('e9', 'done')
    labels['reject'] = len(out)
    emit('c7 07', 3)
    labels['done'] = len(out)
    emit('61 9d')                            # restore entry state
    emit('e9', (base + UPDATE_RVA - (code + len(out) + 5)) & 0xFFFFFFFF)
    if extras:
        from .consumables import emit_anchor_visitor
        emit_anchor_visitor(emit, branch, labels, out, base)
        from .sell_building import emit_sell_visitor
        emit_sell_visitor(emit, branch, labels, out, base)
    for offset, label in branches:
        struct.pack_into('<i', out, offset, labels[label] - (offset + 4))
    return bytes(out)


class PowerOutage:
    allocation_size = 0x3000
    layouts = TABLE_LAYOUTS
    signature = (BROWNOUT_RVA, bytes.fromhex('8a 44 24 04 84 c0 56 57'))

    def make_stub(self, code, mailbox):
        return build_stub(self.game.base, code, mailbox)

    def extra_pages(self, region, mailbox):
        return {}

    def __init__(self, game):
        self.game = game
        self.logic = self.region = self.table = self.mailbox = 0
        self.original = 0
        self.reported = True
        self.install_failed = False

    def _write(self, handle, address, data):
        if len(data) > 512:
            for offset in range(0, len(data), 512):
                self._write(handle, address + offset, data[offset:offset + 512])
            return
        written = ct.c_size_t()
        buffer = ct.create_string_buffer(data)
        if (not self.game.api.WriteProcessMemory(handle, address, buffer, len(data), ct.byref(written))
                or written.value != len(data) or self.game.read(address, len(data)) != data):
            raise MemoryReadError('Power hook data write failed verification.')

    def install(self, state):
        game = self.game
        if self.install_failed:
            raise MemoryReadError('Power hook installation was incomplete; restart Zero Hour before retrying.')
        if self.region:
            if state.logic != self.logic or game.pointer(self.logic) != self.table:
                raise MemoryReadError('Power update hook changed; restart Zero Hour before retrying.')
            return
        original = game.pointer(state.logic)
        layout = self.layouts.get(original - game.base)
        if layout is None or game.read(original, len(layout) * 4) != struct.pack(f'<{len(layout)}I', *(game.base + rva for rva in layout)):
            raise MemoryReadError('Unsupported or already hooked game update table. Close other clients and restart Zero Hour.')
        signature_rva, signature = self.signature
        if game.read(game.base + signature_rva, len(signature)) != signature_bytes(game.base, signature, signature_rva):
            raise MemoryReadError('Native callback does not match the supported Steam build.')
        handle = game.api.OpenProcess(0x1038, False, game.pid)
        if not handle:
            raise windows_error('install power update', game.pid, ct.get_last_error())
        try:
            region = game.api.VirtualAllocEx(handle, None, self.allocation_size, 0x3000, 0x04)
            if not region or region + self.allocation_size > 0xFFFFFFFF:
                raise MemoryReadError('Could not allocate the power update hook.')
            self.install_failed = True
            # Keep RTTI prefix and all original virtual methods, except update.
            table, mailbox = region + 0x1004, region + 0x2000
            vtable = bytearray(game.read(original - 4, 4 + len(layout) * 4))
            struct.pack_into('<I', vtable, 4 + 4 * 4, region)
            self._write(handle, region, self.make_stub(region, mailbox))
            self._write(handle, table - 4, bytes(vtable))
            self._write(handle, mailbox, bytes(28))
            extra = self.extra_pages(region, mailbox)
            for address, data in extra.items():
                if len(data) > 0x1000:
                    raise MemoryReadError('Additional callback exceeds its code page.')
                self._write(handle, address, data)
            old = wt.DWORD()
            for address, protection in ((region, 0x20), (region + 0x1000, 0x02), *((a, 0x20) for a in extra)):
                if not game.api.VirtualProtectEx(handle, address, 0x1000, protection, ct.byref(old)):
                    raise MemoryReadError('Could not protect the power hook pages.')
            if not game.api.FlushInstructionCache(handle, region, 0x1000):
                raise MemoryReadError('Could not synchronize the power hook code.')
            for address in extra:
                if not game.api.FlushInstructionCache(handle, address, 0x1000):
                    raise MemoryReadError('Could not synchronize the additional callback.')
            # Record ownership before publishing, including uncertain writes.
            self.logic, self.region, self.table, self.mailbox = state.logic, region, table, mailbox
            self.original = original
            game.replace_pointer(state.logic, original, table)
            self.install_failed = False
        finally:
            game.api.CloseHandle(handle)

    def poll(self):
        if not self.mailbox or self.reported:
            return []
        status = self.game.pointer(self.mailbox)
        if status in (1, 4):
            return []
        self.reported = True
        if status == 2:
            return ['Power Outage Trap applied: native building/radar brownout activated; the game restores power when the timer expires.']
        raise MemoryReadError('Power request was rejected after a mission transition; its reserved receipt will not replay automatically.')

    @property
    def busy(self):
        return bool(self.mailbox and self.game.pointer(self.mailbox) in (1, 4))

    def prepare(self, state, count):
        self.install(state)
        if self.busy:
            raise MemoryReadError('A power request is waiting for the next simulation update. Resume the game.')
        manager = self.game.pointer(self.game.base + CAMPAIGN_GLOBAL_RVA)
        if not manager:
            raise MemoryReadError('Campaign changed before power request.')
        raw = self.game.read(manager + 8, 9)
        campaign, mission, victory = struct.unpack('<IIB', raw)
        if not campaign or not mission or victory:
            raise MemoryReadError('Mission ended before power request.')
        duration = count * getattr(self, "power_seconds", 30) * 30
        if duration > 0xFFFFFFFF:
            raise MemoryReadError('Power trap duration overflow.')
        # status remains idle/done while fields are filled. Publish last.
        for offset, value in ((4, state.player), (8, state.frame), (12, duration),
                              (16, campaign), (20, mission)):
            address = self.mailbox + offset
            self.game.replace_pointer(address, self.game.pointer(address), value)

    def arm(self):
        self.reported = False
        self.game.replace_pointer(self.mailbox, self.game.pointer(self.mailbox), 1)

    def close(self):
        if not self.region:
            return
        # Never free published code: an update may already have loaded its address.
        # At most one pending request can finish; it has a persisted receipt.
        if self.game.pointer(self.logic) == self.table:
            self.game.replace_pointer(self.logic, self.table, self.original)
