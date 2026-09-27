"""Persistent AP point budget, reconciled on the simulation thread.

The engine saves AcademyStats::m_generalsPointsSpent with the Player. Using that
counter preserves mission grants and makes saves/checkpoints naturally account
for purchases without keeping a second, potentially divergent purchase ledger.
"""
import math
import struct

from .memory import MemoryReadError, CAMPAIGN_GLOBAL_RVA
from .power import GAME_LOGIC_RVA, PLAYER_LIST_RVA, ENERGY_VTABLE_RVA
from .gameplay import input_enabled, UI_RVA, UI_TABLE_RVA, INPUT_OFFSET
from .mission_data import GENERALS_POINT_ID

SET_RANK, POINTS_CHANGED, CONTROL_BAR, RANK_STORE = 0x55B00, 0x5EC80, 0x6395F8, 0x63989C
ENABLED, PLAYER, CAMPAIGN, MISSION, FRAME, BUDGET = range(0x800, 0x818, 4)
RANK_IDS = 0x820
SCIENCES, RANK, POINTS, SPENT, XP_MODIFIER = 0x164, 0x188, 0x190, 0x1E4, 0x264
THRESHOLDS = (1, 2, 3, 4, 7)
SIGNATURES = ((SET_RANK, '5156578b7c241083'),
              (POINTS_CHANGED, '568bf18b4c2408'),
              (0x55280, '558bec51db450853'), (0x5587F, '578bce'))


def rank_for_points(points):
    return max(1, sum(points >= n for n in THRESHOLDS))


def build_points_stub(base, mailbox):
    out, labels, jumps = bytearray(), {}, []
    def e(h, *words):
        out.extend(bytes.fromhex(h))
        for value in words: out.extend(struct.pack('<I', value))
    def j(h, label):
        e(h); jumps.append((len(out), label)); e('00000000')
    def call(rva):
        e('b8', base + rva); e('ff d0')
    e('9c 60 bf', mailbox)
    e('83 bf', ENABLED); e('01'); j('0f 85', 'done')
    e('3b 0d', base + GAME_LOGIC_RVA); j('0f 85', 'done')
    for offset in (0x51, 0x52, 0x64):
        e(f'80 79 {offset:02x} 00'); j('0f 85', 'done')
    e('83 b9 94 00 00 00 00'); j('0f 85', 'done')
    e('8b 41 3c 3b 87', FRAME); j('0f 82', 'done')
    e('a1', base + PLAYER_LIST_RVA); e('85 c0'); j('0f 84', 'done')
    e('8b 70 0c 85 f6'); j('0f 84', 'done')
    e('3b b7', PLAYER); j('0f 85', 'done')
    e('81 be 80 00 00 00', base + ENERGY_VTABLE_RVA); j('0f 85', 'done')
    e('39 b6 90 00 00 00'); j('0f 85', 'done')
    e('a1', base + CAMPAIGN_GLOBAL_RVA); e('85 c0'); j('0f 84', 'done')
    e('80 78 10 00'); j('0f 85', 'done')
    for source, target in ((8, CAMPAIGN), (12, MISSION)):
        e(f'8b 50 {source:02x} 3b 97', target); j('0f 85', 'done')
    e('a1', base + UI_RVA); e('85 c0'); j('0f 84', 'done')
    e('81 38', base + UI_TABLE_RVA); j('0f 85', 'done')
    e(f'80 78 {INPUT_OFFSET:02x} 01'); j('0f 85', 'done')
    # Bounded, aligned native science vector. Validate before changing rank.
    e('8b 9e', SCIENCES); e('8b ae', SCIENCES + 4)
    e('89 e8 29 d8'); j('0f 82', 'done')
    e('a9 03 00 00 00'); j('0f 85', 'done')
    e('3d 00 10 00 00'); j('0f 87', 'done')
    e('81 fb 00 00 01 00'); j('0f 82', 'done')
    e('81 be', SPENT, 1000000); j('0f 87', 'done')
    e('81 bf', BUDGET, 1000000); j('0f 87', 'done')
    e('8b 87', BUDGET); e('ba 01 00 00 00')
    for threshold, rank in ((2, 2), (3, 3), (4, 4), (7, 5)):
        e(f'83 f8 {threshold:02x}'); j('0f 82', 'rank_ready')
        e('ba', rank)
    labels['rank_ready'] = len(out)
    e('8b 0d', base + GAME_LOGIC_RVA); e('8b 89 98 00 00 00')
    e('83 f9 01'); j('0f 82', 'done')
    # GameLogic initializes/resets the cap to 1000 (unlimited), including
    # challenge missions. Story scripts commonly replace it with ranks 1..5.
    # The sentinel is valid; rejecting it skips the entire point reconciliation.
    e('81 f9', 1000); j('0f 84', 'cap_ready')
    e('83 f9 05'); j('0f 87', 'done')
    labels['cap_ready'] = len(out)
    e('39 ca 0f 4f d1')  # min(point-derived rank, mission rank limit)
    e('c7 86', XP_MODIFIER, 0)  # affects general XP, not unit veterancy
    e('39 96', RANK); j('0f 84', 'balance')
    # Remove only rank sciences, preserving purchased and mission-granted
    # sciences. setRankLevel's normal downward path would erase all of them.
    e('52 89 d9')  # save desired rank; output cursor=begin
    labels['filter'] = len(out)
    e('39 eb'); j('0f 83', 'filtered')
    e('8b 03')
    for offset in range(RANK_IDS, RANK_IDS + 20, 4):
        e('3b 87', offset); j('0f 84', 'skip')
    e('89 01 83 c1 04')
    labels['skip'] = len(out)
    e('83 c3 04'); j('e9', 'filter')
    labels['filtered'] = len(out)
    e('89 8e', SCIENCES + 4)
    # Start its upward loop at rank 1; never call native resetSciences.
    e('c7 86', RANK, 0); e('c7 86', RANK + 4, 0)
    e('89 f1'); call(SET_RANK)  # consumes saved desired-rank argument
    labels['balance'] = len(out)
    e('8b 87', BUDGET); e('2b 86', SPENT)
    e('ba 00 00 00 00 0f 48 c2')  # max(total received - saved spent, 0)
    e('39 86', POINTS); j('0f 84', 'done')
    e('89 86', POINTS)
    e('8b 0d', base + CONTROL_BAR); e('85 c9'); j('0f 84', 'done')
    e('56'); call(POINTS_CHANGED)
    labels['done'] = len(out)
    e('61 9d c3')
    for offset, label in jumps: struct.pack_into('<i', out, offset, labels[label] - offset - 4)
    return bytes(out)


class GeneralsPoints:
    def __init__(self, effects):
        self.effects = effects
        self.last = None
        self.original_xp = None
        self.reported = None
        self.mission = None

    def rank_ids(self):
        game = self.effects.game
        store = game.pointer(game.base + RANK_STORE)
        if not store: raise MemoryReadError('Rank definitions are not loaded.')
        begin, end = struct.unpack('<II', game.read(store + 8, 8))
        if not begin or end - begin != 20:
            raise MemoryReadError('Unsupported rank definition layout.')
        ids = []
        for i, threshold in enumerate((0, 800, 1500, 2500, 5000)):
            entry = game.pointer(begin + i * 4)
            for _ in range(16):
                child = game.pointer(entry + 4)
                if not child: break
                entry = child
            else: raise MemoryReadError('Rank override chain is invalid.')
            skill, grant, first, last = struct.unpack('<4I', game.read(entry + 0x10, 16))
            if skill != threshold or grant != (3 if i == 4 else 1) or not first or last - first != 4:
                raise MemoryReadError('Unsupported general rank thresholds.')
            ids.append(game.pointer(first))
        if len(set(ids)) != 5 or any(n > 0xFFFF for n in ids):
            raise MemoryReadError('Invalid rank science identities.')
        return ids

    def apply(self, state, inventory):
        game, power = self.effects.game, self.effects.power
        if not state or not state.player or state.loading_map or state.loading_save:
            self.disable()
            return []
        if not input_enabled(game): return []
        # Resolved layout anchors verify XP modifier and saved purchase offset.
        for rva in (SET_RANK, POINTS_CHANGED, 0x55280, 0x5587F):
            _ = game.base + rva
        ids = self.rank_ids()
        first, last, capacity = struct.unpack('<III', game.read(state.player + SCIENCES, 12))
        if not 0x10000 <= first <= last <= capacity or (last - first) % 4 or capacity - first > 0x1000:
            raise MemoryReadError('Unsupported player science vector.')
        game.read(first, last - first)
        if not 0 <= game.pointer(state.player + RANK) <= 5 or game.pointer(state.player + SPENT) > 1000000:
            raise MemoryReadError('Unsupported player rank or purchase counter.')
        self.effects.check_same(state)
        power.install(state)
        mb = power.mailbox
        manager = game.pointer(game.base + CAMPAIGN_GLOBAL_RVA)
        campaign, mission = struct.unpack('<II', game.read(manager + 8, 8))
        key = (state.player, campaign, mission)
        if key != self.last:
            xp = struct.unpack('<f', game.read(state.player + XP_MODIFIER, 4))[0]
            if not math.isfinite(xp) or not 0 <= xp <= 100:
                raise MemoryReadError('Invalid general XP modifier.')
            self.original_xp = xp or 1.0  # AP saves already contain the zero modifier
            self.last = key
            self.mission = state.mission
        budget = inventory.count(GENERALS_POINT_ID)
        if not 0 <= budget <= 1000000: raise MemoryReadError('Generals point count is out of range.')
        def put(offset, value):
            address = mb + offset
            old = game.pointer(address)
            if old != value: game.replace_pointer(address, old, value)
        put(ENABLED, 0)
        for offset, value in ((PLAYER, state.player), (CAMPAIGN, campaign), (MISSION, mission),
                              (FRAME, state.frame), (BUDGET, budget),
                              *((RANK_IDS + i*4, value) for i, value in enumerate(ids))):
            put(offset, value)
        put(ENABLED, 1)
        report = (key, budget)
        if report != self.reported:
            self.reported = report
            return [f'Progressive Generals Points: {budget} total; rank follows received points, not XP. Each mission has its own purchases.']
        return []

    def disable(self):
        power = self.effects.power
        if power and power.mailbox:
            address = power.mailbox + ENABLED
            old = self.effects.game.pointer(address)
            if old: self.effects.game.replace_pointer(address, old, 0)

    def close(self):
        self.disable()
        state = self.effects.snapshot()
        if (state and not state.loading_map and not state.loading_save and self.last
                and state.player == self.last[0] and state.mission == self.mission
                and self.original_xp is not None):
            game = self.effects.game
            address = state.player + XP_MODIFIER
            if game.pointer(address) == 0:
                game.replace_pointer(address, 0, struct.unpack('<I', struct.pack('<f', self.original_xp))[0])
