"""Player-control flag shared by post-intro cash and checkpoint capture."""
from .memory import MemoryReadError

UI_RVA = 0x639FB0
UI_TABLE_RVA = 0x569E30
INPUT_OFFSET = 0xD


def input_enabled(game):
    ui = game.pointer(game.base + UI_RVA)
    if not ui:
        return False
    if game.pointer(ui) != game.base + UI_TABLE_RVA:
        raise MemoryReadError('Player-control layout is unsupported.')
    flag = game.read(ui + INPUT_OFFSET, 1)
    if flag not in (b'\0', b'\1'):
        raise MemoryReadError('Invalid player-control flag.')
    return flag == b'\1'
