"""Mission failure observation and native Restart Mission dispatch on the GUI loop."""
from dataclasses import dataclass
from types import SimpleNamespace
import struct

from .power import PowerOutage
from .memory import CAMPAIGN_GLOBAL_RVA, MemoryReadError
from .dozer import GAME_LOGIC_RVA
from .mission_data import ALL_BY_CAMPAIGN_MISSION

SCRIPT_ENGINE_RVA = 0x639580
SCRIPT_VTABLE_RVA = 0x545D08
END_TIMER_OFFSET = 0x10AA4
GAME_CLIENT_RVA = 0x639B18
RESTART_RVA = 0x1CB1E0
CLIENT_UPDATE_RVA = 0x374AF0
CLIENT_TABLE_RVA = 0x569064
CLIENT_TABLE = tuple(int(v, 16) for v in (
    '374aa0 374ae0 21d640 374b00 374af0 21d640 447400 a9ad0 a8960 21590 '
    'aa4f0 aa540 aa520 374c50 374c00 aa390 8b830 aa050 374b10 aa160 '
    '374cd0 1d02b0 1d02b0 21570 374d10 374d40 aa560 aa580 aa5a0 21590 '
    '374dd0 374690 3746f0 374750 3747b0 374830 374890 3748f0 3749d0 '
    '374a30 374950 3749b0 374800').split())


@dataclass(frozen=True)
class MissionState:
    logic: int
    frame: int
    campaign: int
    mission: int
    location: int
    failed: bool


def mission_state(game):
    logic = game.pointer(game.base + GAME_LOGIC_RVA)
    if not logic or game.pointer(logic + 0x94) != 0:
        return None
    if any(game.read(logic + 0x51, 2)) or game.read(logic + 0x64, 1) != b'\0':
        return None
    frame = game.pointer(logic + 0x3C)
    if frame < 30:
        return None
    manager = game.pointer(game.base + CAMPAIGN_GLOBAL_RVA)
    if not manager:
        return None
    before = game.read(manager + 8, 9)
    snapshot = game.snapshot()
    if not snapshot or snapshot.victorious:
        return None
    mission = ALL_BY_CAMPAIGN_MISSION.get((snapshot.campaign, snapshot.mission))
    if not mission or mission['map'] != snapshot.map_name:
        return None
    scripts = game.pointer(game.base + SCRIPT_ENGINE_RVA)
    if not scripts or game.pointer(scripts) != game.base + SCRIPT_VTABLE_RVA:
        raise MemoryReadError('DeathLink: ScriptEngine layout does not match the supported game.')
    timer = struct.unpack('<i', game.read(scripts + END_TIMER_OFFSET, 4))[0]
    if not -1 <= timer <= 120:
        raise MemoryReadError(f'DeathLink: unexpected mission-end timer {timer}.')
    if game.read(manager + 8, 9) != before or any(game.read(logic + 0x51, 2)):
        return None
    campaign, mission_pointer, victorious = struct.unpack('<IIB', before)
    if victorious or not campaign or not mission_pointer:
        return None
    return MissionState(logic, frame, campaign, mission_pointer, mission['id'], timer >= 0)


class FailureDetector:
    def __init__(self):
        self.armed = None
        self.suppressed = None

    def reset(self):
        self.armed = self.suppressed = None

    def suppress(self, state):
        self.armed = None
        self.suppressed = state

    def observe(self, state):
        if state is None:
            self.reset()
            return None
        key = (state.logic, state.campaign, state.mission)
        if self.suppressed:
            old = self.suppressed
            if key == (old.logic, old.campaign, old.mission) and state.frame >= old.frame:
                return None
            self.suppressed = None
        if not state.failed:
            self.armed = key
            return None
        armed, self.armed = self.armed, None
        return state.location if armed == key else None


def build_restart_stub(base, code, mailbox, quick=False, gate=False):
    out, labels, jumps = bytearray(), {}, []
    def emit(hex_bytes, *words):
        out.extend(bytes.fromhex(hex_bytes))
        for word in words:
            out.extend(struct.pack('<I', word))
    def branch(op, label):
        emit(op); jumps.append((len(out), label)); emit('00 00 00 00')
    emit('9c 60 bf', mailbox)
    emit('83 3f 01'); branch('0f 85', 'done')
    emit('b8', 1); emit('ba', 4); emit('f0 0f b1 17'); branch('0f 85', 'done')
    emit('3b 0d', base + GAME_CLIENT_RVA); branch('0f 85', 'reject')
    emit('a1', base + GAME_LOGIC_RVA)
    emit('85 c0'); branch('0f 84', 'reject')
    emit('3b 47 04'); branch('0f 85', 'reject')
    for offset in (0x51, 0x52, 0x64):
        emit(f'80 78 {offset:02x} 00'); branch('0f 85', 'reject')
    emit('83 b8 94 00 00 00 00'); branch('0f 85', 'reject')
    emit('8b 50 3c 3b 57 08'); branch('0f 82', 'reject')
    emit('a1', base + CAMPAIGN_GLOBAL_RVA)
    emit('85 c0'); branch('0f 84', 'reject')
    emit('80 78 10 00'); branch('0f 85', 'reject')
    emit('8b 50 08 3b 57 10'); branch('0f 85', 'reject')
    emit('8b 50 0c 3b 57 14'); branch('0f 85', 'reject')
    emit('a1', base + SCRIPT_ENGINE_RVA)
    emit('85 c0'); branch('0f 84', 'reject')
    emit('81 38', base + SCRIPT_VTABLE_RVA); branch('0f 85', 'reject')
    emit('83 b8 a4 0a 01 00 ff'); branch('0f 85', 'reject')
    if gate:
        from .missiongate import emit_gate_actions
        emit_gate_actions(base, mailbox, emit, branch, labels, out)
    if quick:
        from .quickreset import emit_checkpoint_actions
        emit_checkpoint_actions(base, mailbox, emit, branch, labels, out)
    # Native menu callback: saves difficulty/rank/map, clears game, queues new game.
    emit('b8', base + RESTART_RVA); emit('ff d0')
    emit('c7 07', 2); branch('e9', 'done')
    labels['reject'] = len(out); emit('c7 07', 3)
    labels['done'] = len(out); emit('61 9d')
    emit('e9', (base + CLIENT_UPDATE_RVA - (code + len(out) + 5)) & 0xFFFFFFFF)
    for offset, label in jumps:
        struct.pack_into('<i', out, offset, labels[label] - offset - 4)
    return bytes(out)


class MissionRestart(PowerOutage):
    layouts = {CLIENT_TABLE_RVA: CLIENT_TABLE}
    signature = (RESTART_RVA, bytes.fromhex('64 a1 00 00 00 00'))

    def make_stub(self, code, mailbox):
        return build_restart_stub(self.game.base, code, mailbox)

    def request(self, state):
        client = self.game.pointer(self.game.base + GAME_CLIENT_RVA)
        if not client:
            raise MemoryReadError('DeathLink: game client is unavailable.')
        self.install(SimpleNamespace(logic=client))
        if self.busy:
            return False
        if mission_state(self.game) != state:
            # Frame can advance during installation; compare scene separately.
            fresh = mission_state(self.game)
            if (fresh is None or fresh.failed or fresh.frame < state.frame
                    or (fresh.logic, fresh.campaign, fresh.mission) != (state.logic, state.campaign, state.mission)):
                raise MemoryReadError('DeathLink: mission changed before restart.')
        for offset, value in ((4, state.logic), (8, state.frame),
                              (16, state.campaign), (20, state.mission)):
            address = self.mailbox + offset
            self.game.replace_pointer(address, self.game.pointer(address), value)
        self.arm()
        return True

    def poll(self):
        if not self.mailbox or self.reported:
            return []
        status = self.game.pointer(self.mailbox)
        if status in (1, 4):
            return []
        self.reported = True
        if status == 2:
            return ['DeathLink: native Restart Mission executed.']
        return ['DeathLink: restart cancelled because the mission changed or ended.']
