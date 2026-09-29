"""Timed, local-player build boosts; all mutations run on the simulation thread.

Production adds one frame to the current unit queue before its normal update.
Construction wraps DozerDoActionState::update (also used by GLA workers),
halving only the local player's building build-time handicap for that call.
The exact original bits are restored before returning. Native construction
still handles builder presence, health, power penalties and completion events.
No modified handicap survives a frame, save, disconnect or mission transition.
"""
import struct

from .power import GAME_LOGIC_RVA, PLAYER_LIST_RVA
from .memory import CAMPAIGN_GLOBAL_RVA
from .gameplay import UI_RVA, UI_TABLE_RVA, INPUT_OFFSET

DURATION = 120
PRODUCTION = 0x900
CONSTRUCTION = 0x920
PAGE = 0x4000
MAINTENANCE = PAGE
DISPATCH = PAGE + 0x400
CONSTRUCTION_CODE = PAGE + 0x800
PRODUCTION_CODE = PAGE + 0xC00
DOZER_TABLE = 0x559CEC
DOZER_UPDATE = 0x244AD0
BUILDING_TIME = 0x18  # Player::Handicap[BUILDTIME][BUILDINGS]
SIGNATURES = ((0x177F30, '8b4424088b40688b54240425ff000000c1e8078d0450d90481c20800'),
              (0x18CE60, '83ec085356578b7c24188bf18b86ec010000566a018d4f0c89442418'),
              (DOZER_UPDATE, '6aff'))


class Assembler:
    def __init__(self):
        self.out, self.labels, self.jumps = bytearray(), {}, []
    def e(self, h, *words):
        self.out.extend(bytes.fromhex(h))
        for word in words: self.out.extend(struct.pack('<I', word))
    def j(self, h, label):
        self.e(h); self.jumps.append((len(self.out), label)); self.e('00000000')
    def mark(self, label): self.labels[label] = len(self.out)
    def finish(self):
        for pos, label in self.jumps:
            struct.pack_into('<i', self.out, pos, self.labels[label] - pos - 4)
        return bytes(self.out)


def guard(a, base, timer, failure, expiry=True):
    """EDI=mailbox. Validate timer ownership without dereferencing old players."""
    e,j=a.e,a.j
    e('83 bf', timer); e('00'); j('0f84', failure)
    e('8b 1d', base + GAME_LOGIC_RVA); e('85 db'); j('0f84', failure)
    e('3b 9f', timer+8); j('0f85', failure)
    for off in (0x51,0x52,0x64):
        e(f'80 7b {off:02x} 00'); j('0f85', failure)
    e('83 bb 94 00 00 00 00'); j('0f85', failure)
    e('8b 53 3c 3b 97', timer+12); j('0f82', failure)
    if expiry:
        e('3b 97', timer); j('0f83', failure)
    e('a1', base + PLAYER_LIST_RVA); e('85 c0'); j('0f84', failure)
    e('8b 70 0c 85 f6'); j('0f84', failure)
    e('3b b7', timer+4); j('0f85', failure)
    e('a1', base + CAMPAIGN_GLOBAL_RVA); e('85 c0'); j('0f84', failure)
    e('80 78 10 00'); j('0f85', failure)
    for off in (16,20):
        e(f'8b 48 {off-8:02x} 3b 8f', timer+off); j('0f85', failure)


def control(a, base, failure):
    a.e('a1', base + UI_RVA); a.e('85 c0'); a.j('0f84', failure)
    a.e('81 38', base + UI_TABLE_RVA); a.j('0f85', failure)
    a.e(f'80 78 {INPUT_OFFSET:02x} 01'); a.j('0f85', failure)


def maintenance(base, mailbox):
    a=Assembler(); e,j=a.e,a.j
    e('9c60bf',mailbox)
    for timer in (PRODUCTION,CONSTRUCTION):
        clear,done,paused=(f'{s}{timer}' for s in ('clear','done','paused'))
        guard(a,base,timer,clear,expiry=False)
        control(a,base,paused)
        e('3b 97',timer); j('0f83',clear)
        e('89 97',timer+12); j('e9',done)
        a.mark(paused)
        # Preserve remaining duration during cutscenes; pauses freeze game frames.
        e('89 d0 2b 87',timer+12); e('01 87',timer); j('0f82',clear)
        e('89 97',timer+12); j('e9',done)
        a.mark(clear); e('c7 87',timer,0)
        a.mark(done)
    e('619dc3'); return a.finish()


def dispatch(base, mailbox):
    # Called after the shared item request's mission/control checks. EBX=frame.
    a=Assembler(); e,j=a.e,a.j
    for op,timer in ((8,PRODUCTION),(9,CONSTRUCTION)):
        nxt=f'next{op}'
        e(f'83 7f 1c {op:02x}'); j('0f85',nxt)
        e('8b 87',timer); e('39 d8 0f42c3 03 47 0c'); j('0f82','reject')
        e('89 87',timer); e('89 b7',timer+4); e('89 8f',timer+8)
        e('89 9f',timer+12)
        for off in (16,20): e(f'8b 57 {off:02x} 89 97',timer+off)
        e('89 47 18 c7 07',2); e('c3'); a.mark(nxt)
    a.mark('reject'); e('c7 07',3); e('c3'); return a.finish()


def production(base, mailbox):
    a=Assembler();e,j=a.e,a.j
    e('9c60bf',mailbox)
    guard(a,base,PRODUCTION,'done'); control(a,base,'done')
    e('8b 4c 24 18 8b 69 18 85 ed'); j('0f84','done')
    e('83 7d 04 01'); j('0f85','done')  # not upgrades
    e('8b 49 f8 85 c9'); j('0f84','done')
    e('b8',base+0x148290); e('ffd0 39f0'); j('0f85','done')
    e('81 7d 14 ff ff ff 7f'); j('0f83','done')
    e('ff 45 14')  # native update adds the other frame and performs completion
    a.mark('done'); e('619dc3'); return a.finish()


def construction(base, mailbox):
    a=Assembler();e,j=a.e,a.j
    e('9c60bf',mailbox)
    guard(a,base,CONSTRUCTION,'original'); control(a,base,'original')
    e('8b 4c 24 18 8b 49 20 85 c9'); j('0f84','original')
    e('8b 49 14 85 c9'); j('0f84','original')  # state machine's builder
    e('b8',base+0x148290);e('ffd0 39f0');j('0f85','original')
    e('8b 46 18 3d 00 00 00 01'); j('0f82','original')
    e('3d 00 00 80 7f'); j('0f83','original')  # finite positive normal float
    e('50 56 2d 00 00 80 00 89 46 18')  # save original bits; divide float by 2
    e('8b 4c 24 20 b8',base+DOZER_UPDATE);e('ffd0')
    e('5a59 89 4a 18 89 44 24 1c 619dc3')  # restore handicap; keep native result
    a.mark('original');e('619d b8',base+DOZER_UPDATE);e('ffe0')
    return a.finish()


def page(base, mailbox):
    parts=(maintenance(base,mailbox),dispatch(base,mailbox),construction(base,mailbox),production(base,mailbox))
    if any(len(p)>0x400 for p in parts): raise ValueError('Boost callback exceeds its reserved space')
    return b''.join(p.ljust(0x400,b'\x90') for p in parts)
