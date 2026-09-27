"""Experimental post-intro checkpoints using the game's normal save/load engine.

No cinematic scripts are skipped. Capture once after a fresh map hands control
to the player. A process-specific filename never overwrites manual/quick saves.
"""
import uuid

from .deathlink import MissionRestart, build_restart_stub, mission_state, GAME_LOGIC_RVA
from .compatibility import signature_bytes
from .memory import MemoryReadError
from .mission_data import CASH_ITEM_ID
from .gameplay import input_enabled, UI_RVA, UI_TABLE_RVA, INPUT_OFFSET

GAME_STATE_RVA = 0x639920
SAVE_RVA = 0x8FB40
LOAD_RVA = 0x90000
STRING_CTOR_RVA = 0x1E00


def emit_checkpoint_actions(base, mailbox, emit, branch, labels, out):
    # Opcode at +12: 0 full restart, 1 save, 2 load. All share scene guards.
    emit('83 7f 0c 00'); branch('0f 84', 'full_restart')
    emit('a1', base + GAME_STATE_RVA)
    emit('85 c0'); branch('0f 84', 'reject')
    emit('83 7f 0c 01'); branch('0f 85', 'load')
    # Recheck input on the game thread before taking the checkpoint.
    emit('a1', base + UI_RVA); emit('85 c0'); branch('0f 84', 'reject')
    emit('81 38', base + UI_TABLE_RVA); branch('0f 85', 'reject')
    emit('80 78 0d 01'); branch('0f 85', 'reject')
    # thiscall saveGame(AsciiString, UnicodeString, NORMAL=0, SAVELOAD=0).
    # Construct filename in its by-value argument; callee destroys both strings.
    emit('6a 00 6a 00 6a 00 6a 00 89 e1 68', mailbox + 32)
    emit('b8', base + STRING_CTOR_RVA); emit('ff d0')
    emit('8b 0d', base + GAME_STATE_RVA)
    emit('b8', base + SAVE_RVA); emit('ff d0 89 47 18 85 c0')
    branch('0f 85', 'native_error')
    branch('e9', 'success')
    labels['load'] = len(out)
    emit('83 7f 0c 02'); branch('0f 85', 'reject')
    # AvailableGameInfo is 60 bytes, all nullable strings, NORMAL type at +44.
    # Native loadGame owns/destructs this by-value copy and returns with ret 60.
    emit('6a 00 ' * 15)
    emit('89 e1 68', mailbox + 32)
    emit('b8', base + STRING_CTOR_RVA); emit('ff d0')
    emit('8b 0d', base + GAME_STATE_RVA)
    emit('b8', base + LOAD_RVA); emit('ff d0 89 47 18 85 c0')
    branch('0f 85', 'native_error')
    # Save contains the cash tiers at capture. Add only later consumed tiers.
    # Pending receipts remain pending and are handled normally by PlayerEffects.
    emit('a1', base + 0x6395A0); emit('85 c0'); branch('0f 84', 'reconcile_error')
    emit('8b 70 0c 85 f6'); branch('0f 84', 'reconcile_error')
    emit('81 7e 34', base + 0x5456F0); branch('0f 85', 'reconcile_error')
    emit('81 be 80 00 00 00', base + 0x54F758); branch('0f 85', 'reconcile_error')
    emit('39 b6 90 00 00 00'); branch('0f 85', 'reconcile_error')
    emit('8b 46 38 03 47 1c'); branch('0f 82', 'reconcile_error')
    emit('89 46 38')
    # A trap present in the old snapshot must not be replayed on every reset.
    emit('c7 86 8c 00 00 00', 0)
    emit('31 c0 8b 96 84 00 00 00 3b 96 88 00 00 00 0f 9c c0')
    emit('50 89 f1 b8', base + 0x56C60); emit('ff d0')
    labels['success'] = len(out)
    emit('c7 07', 2); branch('e9', 'done')
    labels['native_error'] = len(out)
    emit('c7 07', 5); branch('e9', 'done')
    labels['reconcile_error'] = len(out)
    emit('c7 07', 6); branch('e9', 'done')
    labels['full_restart'] = len(out)


class QuickReset(MissionRestart):
    def __init__(self, game):
        super().__init__(game)
        self.filename = f'AP-QuickReset-{uuid.uuid4().hex}.sav'
        self.previous = None
        self.loading_map = self.loading_save = False
        self.eligible = False
        self.ready_since = None
        self.checkpoint = None
        self.captured_tiers = 0
        self.pending_tiers = 0
        self.action = 0
        self.restored = False
        self.awaiting_load = False
        self.messages = []

    def make_stub(self, code, mailbox):
        # These entry signatures are from the fingerprinted Steam executable.
        for rva, signature in ((SAVE_RVA, '55 8b ec 6a ff 68 90 1e 90 00'),
                               (LOAD_RVA, '55 8b ec 6a ff 68 54 1f 90 00'),
                               (STRING_CTOR_RVA, '8b 54 24 04 85 d2 56 8b f1')):
            expected = bytes.fromhex(signature)
            if self.game.read(self.game.base + rva, len(expected)) != signature_bytes(self.game.base, expected, rva):
                raise MemoryReadError('Quick Reset: native save/load layout is unsupported.')
        return build_restart_stub(self.game.base, code, mailbox, quick=True)

    @staticmethod
    def key(state):
        return (state.logic, state.campaign, state.mission, state.location)

    @staticmethod
    def tiers(inventory, progress):
        return sum(item.item == CASH_ITEM_ID and i in progress.effect_receipts
                   for i, item in enumerate(inventory.items))

    def input_enabled(self):
        return input_enabled(self.game)

    def observe(self, inventory, progress, effects_ready=True, capture_enabled=True):
        if self.busy:
            return
        logic = self.game.pointer(self.game.base + GAME_LOGIC_RVA)
        if not logic:
            return
        flags = self.game.read(logic + 0x51, 2)
        if any(flags):
            self.loading_map |= bool(flags[0])
            self.loading_save |= bool(flags[1])
            self.ready_since = None
            return
        state = mission_state(self.game)
        if self.awaiting_load:
            if state is not None and not state.failed:
                self.previous = state
                self.checkpoint = self.key(state)
                self.loading_map = self.loading_save = self.awaiting_load = False
            return
        if state is None:
            # A menu/end screen must not provide a reusable checkpoint for a
            # later attempt of the same mission with identical engine pointers.
            if self.game.pointer(logic + 0x94) != 0:
                self.checkpoint = None
                self.eligible = False
            self.ready_since = None
            return
        old = self.previous
        changed = old is None or self.key(old) != self.key(state) or state.frame < old.frame
        if self.loading_map or self.loading_save or changed:
            self.checkpoint = None
            self.eligible = (not self.loading_save and state.frame <= 150
                             and (self.loading_map or changed))
            self.ready_since = None
            self.loading_map = self.loading_save = False
        self.previous = state
        if not capture_enabled:
            self.eligible = False
            self.ready_since = None
            return
        if not self.eligible or state.failed or self.checkpoint:
            return
        if not effects_ready or not self.input_enabled():
            self.ready_since = None
            return
        if self.ready_since is None:
            self.ready_since = state.frame
        if state.frame - self.ready_since < 30:
            return
        self.pending_tiers = self.tiers(inventory, progress)
        self._queue(state, 1)
        self.eligible = False  # no repeated save attempts after a native error

    def _queue(self, state, action, bonus=0, payload=None):
        # Prepare the shared fields without publishing a restart first.
        from types import SimpleNamespace
        from .deathlink import GAME_CLIENT_RVA
        self.install(SimpleNamespace(logic=self.game.pointer(self.game.base + GAME_CLIENT_RVA)))
        if self.busy:
            return False
        fresh = mission_state(self.game)
        if fresh is None or fresh.failed or self.key(fresh) != self.key(state) or fresh.frame < state.frame:
            raise MemoryReadError('Quick Reset: mission changed before dispatch.')
        filename = (self.filename if payload is None else payload).encode('ascii') + b'\0'
        if len(filename) > 400 or b'%' in filename:
            raise MemoryReadError('Invalid mission action text.')
        filename += bytes((-len(filename)) % 4)
        import struct
        values = [(4, state.logic), (8, state.frame), (12, action),
                  (16, state.campaign), (20, state.mission), (24, 0), (28, bonus)]
        values += [(32 + i, struct.unpack_from('<I', filename, i)[0]) for i in range(0, len(filename), 4)]
        for offset, value in values:
            address = self.mailbox + offset
            self.game.replace_pointer(address, self.game.pointer(address), value)
        self.action = action
        self.pending_state = state
        self.arm()
        return True

    def request(self, state, inventory=None, progress=None):
        if self.checkpoint == self.key(state):
            bonus = 5000 * max(0, self.tiers(inventory, progress) - self.captured_tiers)
            if bonus > 0xFFFFFFFF:
                raise MemoryReadError('Quick Reset: cash bonus is too large.')
            return self._queue(state, 2, bonus)
        self.messages.append('DeathLink: no post-intro checkpoint yet; using Option 1 (opening intro replays).')
        return self._queue(state, 0)

    def poll(self):
        messages, self.messages = self.messages, []
        if not self.mailbox or self.reported or self.busy:
            return messages
        status = self.game.pointer(self.mailbox)
        self.reported = True
        if status == 2:
            if self.action == 1:
                self.checkpoint = self.key(self.pending_state)
                self.captured_tiers = self.pending_tiers
                messages.append('Quick Reset: post-intro checkpoint saved. Incoming DeathLinks will load it.')
            elif self.action == 2:
                self.restored = True
                self.awaiting_load = True
                messages.append('DeathLink: Quick Reset checkpoint loaded; later cash unlocks retained, old power trap cleared.')
            else:
                messages.append('DeathLink: native Restart Mission executed (opening intro replays).')
        elif status in (5, 6):
            self.checkpoint = None
            code = self.game.pointer(self.mailbox + 24)
            messages.append(f'Quick Reset failed (status {status}, save/load code {code}); next DeathLink uses Option 1.')
        else:
            messages.append('Quick Reset: request cancelled because the mission changed, ended, or input was disabled.')
            if self.action == 1:
                self.eligible = True  # input may have changed between polls
                self.ready_since = None
        return messages
