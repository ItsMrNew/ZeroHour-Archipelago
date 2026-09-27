"""Show a native mission-lock message, then invoke the normal Exit Mission action."""
import time

from .quickreset import QuickReset
from .deathlink import build_restart_stub
from .gameplay import UI_RVA, UI_TABLE_RVA
from .compatibility import signature_bytes
from .memory import MemoryReadError

EXIT_RVA = 0x1CAFE0  # exitQuitMenu, not quitToDesktop or surrender
MESSAGE_RVA = 0x10B4D0  # InGameUI::message(UnicodeString, ...), cdecl
TRANSLATE_RVA = 0x1FC70  # UnicodeString::translate(const AsciiString&), ret4


def emit_gate_actions(base, mailbox, emit, branch, labels, out):
    emit('83 7f 0c 03'); branch('0f 82', 'gate_pass')
    emit('83 7f 0c 04'); branch('0f 84', 'gate_exit')
    emit('83 7f 0c 03'); branch('0f 85', 'reject')
    emit('a1', base + UI_RVA); emit('85 c0'); branch('0f 84', 'reject')
    emit('81 38', base + UI_TABLE_RVA); branch('0f 85', 'reject')
    # Native owned AsciiString local followed by an owned UnicodeString argument.
    emit('6a 00 89 e1 68', mailbox + 32)
    emit('b8', base + 0x1E00); emit('ff d0')
    emit('6a 00 89 e1 8d 44 24 04 50 b8', base + TRANSLATE_RVA); emit('ff d0')
    emit('a1', base + UI_RVA); emit('50 b8', base + MESSAGE_RVA)
    emit('ff d0 83 c4 08')  # cdecl pops this+format; callee destroys format
    emit('89 e1 b8', base + 0x380F60); emit('ff d0 83 c4 04')
    emit('c7 07', 2); branch('e9', 'done')
    labels['gate_exit'] = len(out)
    emit('b8', base + EXIT_RVA); emit('ff d0')
    emit('c7 07', 2); branch('e9', 'done')
    labels['gate_pass'] = len(out)


class MissionControl(QuickReset):
    def __init__(self, game):
        super().__init__(game)
        self.locked_state = None
        self.lock_reason = None
        self.exit_at = None
        self.exit_sent = False

    def make_stub(self, code, mailbox):
        super().make_stub(code, mailbox)  # validate the existing save/load signatures
        for rva, signature in ((EXIT_RVA, '8b 0d 20 a7 a3 00 53 33 db'),
                               (TRANSLATE_RVA, '83 ec 08 53 55 57')):
            expected = bytes.fromhex(signature)
            if self.game.read(self.game.base + rva, len(expected)) != signature_bytes(self.game.base, expected, rva):
                raise MemoryReadError('Mission lock: native UI/exit layout is unsupported.')
        if self.game.pointer(self.game.base + UI_TABLE_RVA + 0x28) != self.game.base + MESSAGE_RVA:
            raise MemoryReadError('Mission lock: native message layout is unsupported.')
        return build_restart_stub(self.game.base, code, mailbox, quick=True, gate=True)

    def enforce(self, state, reason):
        if state is None or reason is None:
            self.locked_state = self.lock_reason = self.exit_at = None
            self.exit_sent = False
            return False
        if self.busy:
            return True
        old = self.locked_state
        if (old is None or self.key(old) != self.key(state) or state.frame < old.frame
                or reason != self.lock_reason):
            self.locked_state, self.lock_reason = state, reason
            self.exit_at = None
            self.exit_sent = False
            self.checkpoint = None
            self.eligible = False
            self._queue(state, 3, payload=reason + ' Returning to main menu in 5 seconds.')
        elif self.exit_at is not None and time.monotonic() >= self.exit_at and not self.exit_sent:
            self.exit_sent = self._queue(state, 4)
        return True

    def poll(self):
        if self.action < 3:
            return super().poll()
        if not self.mailbox or self.reported or self.busy:
            return []
        self.reported = True
        if self.game.pointer(self.mailbox) != 2:
            self.locked_state = None
            return ['Mission lock action cancelled after a mission transition; will recheck.']
        if self.action == 3:
            if self.lock_reason is None:
                return ['Mission set unlocked; menu return cancelled.']
            self.exit_at = time.monotonic() + 5
            return [self.lock_reason + ' In-game notice shown; returning to menu in 5 seconds.']
        return ['Locked mission exited to the main menu. No check or DeathLink sent.']
