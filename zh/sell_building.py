"""Pick one eligible local structure and invoke the game's normal sale routine."""
import struct

SELL_RVA = 0xB26E0
SIGNATURES = ((SELL_RVA, '64a1000000006aff68fc459000'),)
SEED, COUNT, SELECTED = 0x3C0, 0x3C4, 0x3C8
NO_REFUND, CASH_BEFORE = 0x3CC, 0x3D0
# Object status bits from the stock ObjectStatusTypes enum, at Object+0x80.
INELIGIBLE = (1 << 1) | (1 << 3) | (1 << 4) | (1 << 19) | (1 << 22)


def emit_sell(e, j, labels, out, base, mailbox):
    from .consumables import ASSISTANT_RVA, ASSISTANT_TABLE_RVA, ITERATE_RVA
    labels['sell'] = len(out)
    e('a1', base + ASSISTANT_RVA); e('85 c0'); j('0f 84', 'reject')
    e('81 38', base + ASSISTANT_TABLE_RVA); j('0f 85', 'reject')
    e('c7 87', COUNT, 0); e('c7 87', SELECTED, 0)
    e('57 e8 00 00 00 00 58 05')
    labels['_sell_fix'] = len(out); e('00 00 00 00')
    e('50 89 f1 b8', base + ITERATE_RVA); e('ff d0')
    e('8b 87', SELECTED); e('85 c0'); j('0f 84', 'sell_empty')
    e('8b 50 64 89 57 18')  # report object ID, not a pointer
    e('8b 56 38 89 97', CASH_BEFORE)
    e('50 8b 0d', base + ASSISTANT_RVA)
    e('b8', base + SELL_RVA); e('ff d0')
    e('83 bf', NO_REFUND); e('00'); j('0f 84', 'sell_complete')
    # Normal selling first runs its queue/occupant/parking cleanup. Remove the
    # object before BuildAssistant's delayed payout, then undo any synchronous
    # production refunds. No balance polling or delayed cash subtraction.
    e('ff b7', SELECTED); e('8b 0d', base + 0x639B0C)
    e('b8', base + 0xA4000); e('ff d0')
    e('8b 97', CASH_BEFORE); e('89 56 38')
    labels['sell_complete'] = len(out)
    e('c7 07', 2); j('e9', 'done')
    labels['sell_empty'] = len(out)
    e('c7 47 18', 0); e('c7 07', 6); j('e9', 'done')


def emit_sell_visitor(e, j, labels, out, base):
    from .consumables import KINDOF_RVA, GET_OWNER_RVA
    fix = labels['_sell_fix']
    struct.pack_into('<I', out, fix, len(out) - (fix - 2))
    # cdecl callback(Object*, mailbox). Callee-saved registers protect the
    # iterator and dispatcher even when native thiscall functions clobber ECX.
    e('56 57 8b 74 24 0c 8b 7c 24 10 85 f6'); j('0f 84', 'sell_visit_done')
    e('f6 86 77 02 00 00 09'); j('0f 85', 'sell_visit_done')  # dead/off map
    e('f7 86 80 00 00 00', INELIGIBLE); j('0f 85', 'sell_visit_done')
    e('f6 86 76 02 00 00 04'); j('0f 85', 'sell_visit_done')  # script unsellable
    e('89 f1 b8', base + GET_OWNER_RVA); e('ff d0 3b 47 04'); j('0f 85', 'sell_visit_done')
    e('89 f1 6a 07 b8', base + KINDOF_RVA); e('ff d0 84 c0'); j('0f 84', 'sell_visit_done')
    e('ff 87', COUNT)
    # Reservoir sampling using private xorshift32 state. Never advance the
    # game's random generator or give traversal order a preferred building.
    e('8b 87', SEED)
    e('89 c2 c1 e2 0d 31 d0 89 c2 c1 ea 11 31 d0 89 c2 c1 e2 05 31 d0')
    e('89 87', SEED); e('31 d2 f7 b7', COUNT)
    e('85 d2'); j('0f 85', 'sell_visit_done')
    e('89 b7', SELECTED)
    labels['sell_visit_done'] = len(out)
    e('5f 5e c3')
