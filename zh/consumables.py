"""Verified Steam simulation-thread reinforcement and production effects.

Shares PowerOutage's GameLogic hook. ProductionUpdate's two-entry update
interface gets a guarded dispatcher; enemy production and upgrade research
still call the original routine. No queue entries or unit permissions change.
"""
import ctypes as ct
from ctypes import wintypes as wt
import math
import struct
import secrets

from .power import PowerOutage, build_stub, GAME_LOGIC_RVA, PLAYER_LIST_RVA
from .compatibility import signature_bytes
from .memory import MemoryReadError, CAMPAIGN_GLOBAL_RVA, windows_error
from . import reinforcements as reinforcement
from . import sell_building

PRODUCTION_TABLE_RVA = 0x550C58
PRODUCTION_UPDATE_RVA = 0x1A0D50
GET_OWNER_RVA = 0x148290
ITERATE_RVA = 0x53B10
KINDOF_RVA = 0x144570
FACTORY_RVA = 0x639B24
ASSISTANT_RVA = 0x639B30
ASSISTANT_TABLE_RVA = 0x547E1C
FIND_TEMPLATE_RVA = 0xAD870
BUILD_RVA = 0xB0340
LEGAL_RVA = 0xB16C0
ASCII_CTOR_RVA = 0x1E00
ASCII_DTOR_RVA = 0x380F60
PRODUCTION_CODE_OFFSET = 0xE00
# Timer state is external to saves; it must never become part of a checkpoint.
TIMER = 0x100
ANCHOR = 0x80
TEMPLATE = 0x88
POS = 0x8C
STRING = 0x9C
OFFSETS = 0x200
PLACEMENTS = tuple((radius * math.cos(i * math.pi / 4), radius * math.sin(i * math.pi / 4))
                   for radius in (40, 80, 120) for i in range(8))
NATIVE_SIGNATURES = (
    (PRODUCTION_UPDATE_RVA, '6aff6865509100'), (GET_OWNER_RVA, '8b89b0010000'),
    (ITERATE_RVA, '56578bf98b87a0010000'), (KINDOF_RVA, '8b4104'),
    (FIND_TEMPLATE_RVA, '6aff68ee419000'), (BUILD_RVA, '6aff68a9449000'),
    (LEGAL_RVA, '558bec'), (ASCII_CTOR_RVA, '8b542404'), (ASCII_DTOR_RVA, '568bf18b06'))


def emit_maintenance(e, j, labels, out, base, mailbox):
    """Retire timers at expiry, load, mission change, or frame rewind."""
    e('83 bf', TIMER); e('00')
    j('0f 84', 'maint_done')
    e('3b 0d', base + GAME_LOGIC_RVA)
    j('0f 85', 'clear_timer')
    e('3b 8f', TIMER + 8)
    j('0f 85', 'clear_timer')
    for off in (0x51, 0x52, 0x64):
        e(f'80 79 {off:02x} 00'); j('0f 85', 'clear_timer')
    e('83 b9 94 00 00 00 00'); j('0f 85', 'clear_timer')
    e('8b 41 3c 3b 87', TIMER + 12); j('0f 82', 'clear_timer')
    e('89 87', TIMER + 12)
    e('3b 87', TIMER); j('0f 83', 'clear_timer')
    e('a1', base + PLAYER_LIST_RVA); e('85 c0'); j('0f 84', 'clear_timer')
    e('8b 40 0c 3b 87', TIMER + 4); j('0f 85', 'clear_timer')
    e('a1', base + CAMPAIGN_GLOBAL_RVA); e('85 c0'); j('0f 84', 'clear_timer')
    e('8b 50 08 3b 97', TIMER + 16); j('0f 85', 'clear_timer')
    e('8b 50 0c 3b 97', TIMER + 20); j('0f 85', 'clear_timer')
    j('e9', 'maint_done')
    labels['clear_timer'] = len(out)
    e('c7 87', TIMER, 0)
    labels['maint_done'] = len(out)


def emit_dispatch(e, j, labels, out, base, code, mailbox):
    e('83 7f 1c 00'); j('0f 84', 'power')
    e('83 7f 1c 05'); j('0f 84', 'sell')
    e('83 7f 1c 03'); j('0f 84', 'ability')
    e('83 7f 1c 04'); j('0f 84', 'ability')
    e('83 7f 1c 06'); j('0f 84', 'ability')
    e('83 7f 1c 07'); j('0f 84', 'ability')
    e('83 7f 1c 01'); j('0f 84', 'reinforcements')
    e('83 7f 1c 02'); j('0f 85', 'reject')
    # Extend an existing shutdown, otherwise start at the current frame (ebx).
    e('8b 87', TIMER); e('39 d8 0f 42 c3 03 47 0c'); j('0f 82', 'reject')
    e('89 87', TIMER); e('89 b7', TIMER + 4); e('89 8f', TIMER + 8)
    e('89 9f', TIMER + 12)
    e('8b 57 10 89 97', TIMER + 16)
    e('8b 57 14 89 97', TIMER + 20)
    e('89 47 18 c7 07', 2); j('e9', 'done')

    from .reinforcements import emit_reinforcements
    emit_reinforcements(e, j, labels, out, base, mailbox)
    from .ability_native import emit_ability
    emit_ability(e, j, labels, out, base, mailbox)
    sell_building.emit_sell(e, j, labels, out, base, mailbox)
    labels['power'] = len(out)


def emit_anchor_visitor(e, j, labels, out, base):
    """cdecl callback(Object*, data): prefer live CC, otherwise ground army."""
    here = len(out)
    fix = labels['_anchor_fix']
    # The call-next return is two bytes before the imm32 (pop eax + add eax).
    struct.pack_into('<I', out, fix, here - (fix - 2))
    e('56 57 8b 74 24 0c 8b 7c 24 10 85 f6'); j('0f 84', 'anchor_done')
    e('83 7f 04 02'); j('0f 84', 'anchor_done')
    e('f6 86 77 02 00 00 09'); j('0f 85', 'anchor_done')  # dead / off map
    e('89 f1 6a 0e b8', base + KINDOF_RVA); e('ff d0 84 c0'); j('0f 85', 'anchor_cc')
    e('83 3f 00'); j('0f 85', 'anchor_done')
    e('89 f1 6a 0a b8', base + KINDOF_RVA); e('ff d0 84 c0'); j('0f 85', 'anchor_done')
    e('89 f1 6a 08 b8', base + KINDOF_RVA); e('ff d0 84 c0'); j('0f 85', 'anchor_unit')
    e('89 f1 6a 09 b8', base + KINDOF_RVA); e('ff d0 84 c0'); j('0f 84', 'anchor_done')
    labels['anchor_unit'] = len(out)
    e('89 37 c7 47 04 01 00 00 00'); j('e9', 'anchor_done')
    labels['anchor_cc'] = len(out)
    e('89 37 c7 47 04 02 00 00 00')
    labels['anchor_done'] = len(out)
    e('5f 5e c3')


def build_production_stub(base, code, mailbox):
    out, labels, jumps = bytearray(), {}, []
    def e(h, *words):
        out.extend(bytes.fromhex(h))
        for word in words: out.extend(struct.pack('<I', word))
    def j(h, label):
        e(h); jumps.append((len(out), label)); e('00 00 00 00')
    e('9c 60 bf', mailbox)
    e('8b 87', TIMER); e('85 c0'); j('0f 84', 'original')
    e('8b 1d', base + GAME_LOGIC_RVA); e('85 db'); j('0f 84', 'original')
    e('3b 9f', TIMER + 8); j('0f 85', 'original')
    for off in (0x51, 0x52, 0x64):
        e(f'80 7b {off:02x} 00'); j('0f 85', 'original')
    e('83 bb 94 00 00 00 00'); j('0f 85', 'original')
    e('8b 53 3c 39 c2'); j('0f 83', 'original')
    e('3b 97', TIMER + 12); j('0f 82', 'original')
    e('8b 41 18 85 c0'); j('0f 84', 'original')  # head queue entry
    e('83 78 04 01'); j('0f 85', 'original')      # only PRODUCTION_UNIT
    e('8b 49 f8 85 c9'); j('0f 84', 'original')  # owning Object
    e('b8', base + GET_OWNER_RVA); e('ff d0 3b 87', TIMER + 4)
    j('0f 85', 'original')
    e('61 9d b8 01 00 00 00 c3')                # UPDATE_SLEEP_NONE == 1
    labels['original'] = len(out)
    e('61 9d e9', (base + PRODUCTION_UPDATE_RVA - (code + len(out) + 7)) & 0xFFFFFFFF)
    for pos, label in jumps: struct.pack_into('<i', out, pos, labels[label] - pos - 4)
    return bytes(out)


class CombatEffects(PowerOutage):
    def __init__(self, game, generals=False):
        super().__init__(game)
        self.generals = generals
        self.allocation_size = 0x4000 if generals else 0x3000
        self.operation = 0
        self.production_hooked = False
        self.shutdown_reported_active = False
        self.ability_result = None

    def make_stub(self, code, mailbox):
        main = build_stub(self.game.base, code, mailbox, extras=True, generals=self.generals)
        if len(main) > PRODUCTION_CODE_OFFSET:
            raise MemoryReadError('Item callback exceeds its code page.')
        production = build_production_stub(self.game.base, code + PRODUCTION_CODE_OFFSET, mailbox)
        return main.ljust(PRODUCTION_CODE_OFFSET, b'\x90') + production

    def extra_pages(self, region, mailbox):
        if not self.generals:
            return {}
        from .generals_points import build_points_stub
        return {region + 0x3000: build_points_stub(self.game.base, mailbox)}

    def install(self, state):
        # Verify every new native entry point before publishing any callback.
        from .generals_points import SIGNATURES as generals_signatures
        for rva, prefix in (*NATIVE_SIGNATURES, *reinforcement.SIGNATURES, *sell_building.SIGNATURES,
                            *(generals_signatures if self.generals else ())):
            raw = bytes.fromhex(prefix)
            if self.game.read(self.game.base + rva, len(raw)) != signature_bytes(self.game.base, raw, rva):
                raise MemoryReadError(f'Item callback signature mismatch at {rva:#x}.')
        super().install(state)

    def _production_pointer(self, expected, value):
        game = self.game
        address = game.base + PRODUCTION_TABLE_RVA
        if game.read(address, 8) != struct.pack('<II', expected, game.base + 0x1A0390):
            raise MemoryReadError('Production interface changed; restart Zero Hour before retrying.')
        handle = game.api.OpenProcess(0x1038, False, game.pid)
        if not handle:
            raise windows_error('install production update', game.pid, ct.get_last_error())
        old = wt.DWORD()
        try:
            if not game.api.VirtualProtectEx(handle, address, 4, 0x04, ct.byref(old)):
                raise MemoryReadError('Could not update the production interface protection.')
            try:
                self._write(handle, address, struct.pack('<I', value))
            finally:
                discarded = wt.DWORD()
                if not game.api.VirtualProtectEx(handle, address, 4, old.value, ct.byref(discarded)):
                    raise MemoryReadError('Could not restore the production interface protection.')
        finally:
            game.api.CloseHandle(handle)

    def prepare(self, state, count, operation=0):
        super().prepare(state, count)
        self.operation = operation
        self.game.replace_pointer(self.mailbox + 28, self.game.pointer(self.mailbox + 28), operation)
        if operation == 5:
            address = self.mailbox + sell_building.SEED
            self.game.replace_pointer(address, self.game.pointer(address), secrets.randbelow(0xFFFFFFFF) + 1)
            self.prepare_sale_refund('normal_refund')
        if operation == 2:
            duration = count * getattr(self, "production_seconds", 20) * 30
            if duration > 0xFFFFFFFF:
                raise MemoryReadError('Production shutdown duration overflow.')
            self.game.replace_pointer(self.mailbox + 12, self.game.pointer(self.mailbox + 12), duration)
            if not self.production_hooked:
                self.production_hooked = True  # also tracks uncertain publication
                self._production_pointer(self.game.base + PRODUCTION_UPDATE_RVA,
                                         self.region + PRODUCTION_CODE_OFFSET)
        elif operation == 1:
            assistant = self.game.pointer(self.game.base + ASSISTANT_RVA)
            if (not assistant or self.game.pointer(assistant) != self.game.base + ASSISTANT_TABLE_RVA
                    or not self.game.pointer(self.game.base + FACTORY_RVA)):
                raise MemoryReadError('Reinforcement factory is unavailable; waiting for the mission.')
            # Fill bounded data, not executable memory. Native strings are constructed on game thread.
            handle = self.game.api.OpenProcess(0x1038, False, self.game.pid)
            if not handle:
                raise windows_error('prepare reinforcements', self.game.pid, ct.get_last_error())
            try:
                self._write(handle, self.mailbox + reinforcement.NAMES,
                            b''.join(name.encode('ascii').ljust(48, b'\0') for name in reinforcement.RECIPE))
                self._write(handle, self.mailbox + OFFSETS,
                            b''.join(struct.pack('<ff', *pair) for pair in PLACEMENTS))
            finally:
                self.game.api.CloseHandle(handle)

    def prepare_sale_refund(self, mode):
        if mode not in ('normal_refund', 'no_refund'):
            raise MemoryReadError('Unsupported sale refund setting.')
        address = self.mailbox + sell_building.NO_REFUND
        self.game.replace_pointer(address, self.game.pointer(address), int(mode == 'no_refund'))

    def prepare_ability(self, state, operation, target, radius, lifetime):
        from . import ability_native as a
        signatures = {0xADB30: '568b74240885f657', 0x1440A0: '83ec70568bf18b46',
            0x14DF30: 'd9442404568bf1d8', 0x244190: '8a0da541a800b001',
            0x149F90: '53568bb16c010000', 0x244220: '8b442408566a3868',
            0xA4000: '5156578bf98b4c24', 0xBE220: '568b7424085768f4',
            0xBDEF0: '518b4104568b3157', 0x4B270: '83ec28535556578b',
            a.FINAL_OVERRIDE: '8bc18b500485d274', a.OBJECT_TEMPLATE: '8b410485c07501c3',
            a.CHUTE_DESTINATION: '8b542404568b328d'}
        for rva, signature in signatures.items():
            if self.game.read(self.game.base + rva, 8) != signature_bytes(self.game.base, bytes.fromhex(signature), rva):
                raise MemoryReadError('Unsupported native ability function.')
        bounds = a.map_bounds(self.game)
        if (operation not in (3, 4, 6, 7) or len(target) != 3 or not all(math.isfinite(v) for v in target)
                or not all(bounds[i] <= target[i] <= bounds[i + 3] for i in (0, 1))
                or not 0 < radius <= 150000 or lifetime not in (450, 1200)):
            raise MemoryReadError('Invalid ability target.')
        terrain = self.game.pointer(self.game.base + a.TERRAIN_RVA)
        if operation in (4, 6) and (not terrain or self.game.pointer(terrain) != self.game.base + 0x568F58):
            raise MemoryReadError('Airdrop/strike terrain is unavailable.')
        self.prepare(state, 1, operation)
        handle = self.game.api.OpenProcess(0x1038, False, self.game.pid)
        if not handle:
            raise MemoryReadError('Could not prepare ability data.')
        try:
            template = b'RepairVehiclesInArea_InvisibleMarker_Level3' if operation == 7 else b'SuperweaponPing'
            self._write(handle, self.mailbox + 32, (template + b'\0').ljust(48, b'\0'))
            self._write(handle, self.mailbox + a.OCL_NAME,
                        b'SUPERWEAPON_Paradrop1\0' if operation == 6 else b'AirF_SUPERWEAPON_CarpetBomb\0')
            if operation == 6:
                from .ability_assets import PATRIOT_TEMPLATE
                self._write(handle, self.mailbox + a.DROP_NAME, PATRIOT_TEMPLATE.encode('ascii') + b'\0')
                self._write(handle, self.mailbox + a.CHUTE_NAME, b'LargeParachute\0')
                # Keep all three landing pads inside the map near edge clicks.
                center = max(bounds[0] + 90, min(target[0], bounds[3] - 90))
                self._write(handle, self.mailbox + a.DROP_SPACING,
                            struct.pack('<3f', *(center + dx - target[0] for dx in (-70, 0, 70))))
            self._write(handle, self.mailbox + a.STAGE, bytes(8))
            self._write(handle, self.mailbox + a.TARGET, struct.pack('<4fI', *target, radius, lifetime))
        finally:
            self.game.api.CloseHandle(handle)

    def clear_transient(self):
        if self.mailbox:
            address = self.mailbox + TIMER
            self.game.replace_pointer(address, self.game.pointer(address), 0)

    def poll(self):
        if self.mailbox and self.shutdown_reported_active and not self.game.pointer(self.mailbox + TIMER):
            self.shutdown_reported_active = False
            return ['Production Shutdown ended or cleared by reset; normal unit training restored.']
        if not self.mailbox or self.reported or self.busy:
            return []
        status = self.game.pointer(self.mailbox)
        if self.operation == 0:
            return super().poll()
        self.reported = True
        if self.operation == 5:
            if status == 6:
                return ['Sell Random Building: no eligible building; trap consumed without a sale.']
            if status == 2:
                mode = 'with no refund' if self.game.pointer(self.mailbox + sell_building.NO_REFUND) else 'with the normal refund'
                return [f'Sell Random Building: selling building #{self.game.pointer(self.mailbox + 24)} {mode}.']
            raise MemoryReadError('Building sale cancelled after a mission transition; reserved receipt will not replay.')
        if self.operation in (3, 4, 6, 7):
            self.ability_result = (self.operation, status)
            name = {3: 'Reveal Minimap', 4: 'Carpet Bomb', 6: 'Patriot Airdrop', 7: 'Emergency Repair'}[self.operation]
            if status == 5:
                if self.operation == 6:
                    from .ability_native import DROP_COUNT
                    return [f'Patriot Airdrop: verified {self.game.pointer(self.mailbox + DROP_COUNT)}/3 '
                            'Patriots aboard the plane; cargo setup incomplete, cooldown retained.']
                return [name + ': native strike creation could not be confirmed; cooldown retained.']
            if status == 2:
                if self.operation == 6:
                    from .ability_native import TARGET
                    x, y, _ = struct.unpack('<3f', self.game.read(self.mailbox + TARGET, 12))
                    return [f'Patriot Airdrop: 3/3 Patriot passengers verified aboard the plane; '
                            f'landing destinations set around ({x:.0f}, {y:.0f}).']
                return [name + ' activated.']
            from .ability_native import rejection_detail
            return [name + ' cancelled at ' + rejection_detail(self.game, self.mailbox)
                    + '; cooldown restored.']
        if status != 2:
            raise MemoryReadError('Item request rejected after a transition or missing spawn anchor; reserved receipt will not replay.')
        if self.operation == 1:
            counts = tuple(self.game.pointer(self.mailbox + offset) for offset in
                           (reinforcement.AGENT_COUNT, reinforcement.VEHICLE_COUNT, reinforcement.PASSENGER_COUNT))
            agents, humvee, passengers = counts
            return [f'Reinforcements: {agents}/3 CIA Agents, {humvee}/1 Heroic Humvee with '
                    f'{passengers}/5 Heroic Missile Defenders loaded.'
                    + (' Partial delivery: placement or native unit setup failed; this item will not replay.'
                       if counts != (3, 1, 5) else '')]
        self.shutdown_reported_active = True
        return ['Production Shutdown applied: unit training paused for 20 additional simulation seconds; queues are retained.']

    def close(self):
        self.clear_transient()
        if self.production_hooked:
            address = self.game.base + PRODUCTION_TABLE_RVA
            if self.game.pointer(address) == self.region + PRODUCTION_CODE_OFFSET:
                self._production_pointer(self.region + PRODUCTION_CODE_OFFSET,
                                         self.game.base + PRODUCTION_UPDATE_RVA)
            self.production_hooked = False
        super().close()
