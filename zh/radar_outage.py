"""Suppress only the local minimap callbacks during an AP Power Outage.

Campaigns can force radar on, and some radar providers ignore brownouts. Wrapping
the HUD draw/input callbacks handles both without changing those mission flags,
radar-provider counts, explored terrain, or the saved player state.
"""
from .power import GAME_LOGIC_RVA, PLAYER_LIST_RVA
from .memory import CAMPAIGN_GLOBAL_RVA, MemoryReadError

RADAR = 0x639B00
NEW_MAP = 0x99BD0
DRAW = 0x3C88D0
INPUT = 0x89930
WINDOW = 0x1330
INPUT_FIELD = 0x1D8
DRAW_FIELD = 0x1E0
TIMER = 0xA00  # expiry, player, logic, last frame, campaign, mission
PAGE = 0x5000
DRAW_CODE = PAGE + 0x400
INPUT_CODE = PAGE + 0x800


def record(e):
    # EAX=expiry, ESI=local player, ECX=GameLogic, EBX=current frame.
    e('89 87', TIMER); e('89 b7', TIMER + 4); e('89 8f', TIMER + 8)
    e('89 9f', TIMER + 12)
    for offset in (16, 20):
        e(f'8b 57 {offset:02x} 89 97', TIMER + offset)


def guard(a, base, fail):
    e, j = a.e, a.j
    e('83 bf', TIMER); e('00'); j('0f84', fail)
    e('8b 1d', base + GAME_LOGIC_RVA); e('85 db'); j('0f84', fail)
    e('3b 9f', TIMER + 8); j('0f85', fail)
    for off in (0x51, 0x52, 0x64):
        e(f'80 7b {off:02x} 00'); j('0f85', fail)
    e('83 bb 94 00 00 00 00'); j('0f85', fail)
    e('8b 53 3c 3b 97', TIMER + 12); j('0f82', fail)
    e('3b 97', TIMER); j('0f83', fail)
    e('a1', base + PLAYER_LIST_RVA); e('85 c0'); j('0f84', fail)
    e('8b 70 0c 85 f6'); j('0f84', fail)
    e('3b b7', TIMER + 4); j('0f85', fail)
    e('a1', base + CAMPAIGN_GLOBAL_RVA); e('85 c0'); j('0f84', fail)
    e('80 78 10 00'); j('0f85', fail)
    for off in (16, 20):
        e(f'8b 48 {off-8:02x} 3b 8f', TIMER + off); j('0f85', fail)


def page(base, code, mailbox):
    from .boosts import Assembler
    a = Assembler(); e, j = a.e, a.j
    e('9c60bf', mailbox)
    guard(a, base, 'clear')
    e('89 97', TIMER + 12)  # advance rewind detection
    e('a1', base + RADAR); e('85 c0'); j('0f84', 'done')
    e('8b 80', WINDOW); e('85 c0'); j('0f84', 'done')
    # Only replace the stock callbacks (or our own); leave foreign HUDs alone.
    for field, native, wrapper in ((INPUT_FIELD, INPUT, INPUT_CODE), (DRAW_FIELD, DRAW, DRAW_CODE)):
        e('81 b8', field, base + native); j('0f84', f'install{field}')
        e('81 b8', field, code + wrapper); j('0f85', 'done')
        a.mark(f'install{field}')
    e('c7 80', INPUT_FIELD, code + INPUT_CODE)
    e('c7 80', DRAW_FIELD, code + DRAW_CODE)
    j('e9', 'done')
    a.mark('clear'); e('c7 87', TIMER, 0)
    e('a1', base + RADAR); e('85 c0'); j('0f84', 'done')
    e('8b 80', WINDOW); e('85 c0'); j('0f84', 'done')
    for field, native, wrapper in ((INPUT_FIELD, INPUT, INPUT_CODE), (DRAW_FIELD, DRAW, DRAW_CODE)):
        e('81 b8', field, code + wrapper); j('0f85', f'restored{field}')
        e('c7 80', field, base + native)
        a.mark(f'restored{field}')
    a.mark('done'); e('619dc3')
    result = a.finish()
    assert len(result) <= 0x400
    for offset, native, is_input in ((DRAW_CODE, DRAW, False), (INPUT_CODE, INPUT, True)):
        a = Assembler(); e, j = a.e, a.j
        e('9c60bf', mailbox)
        guard(a, base, 'original')
        e('619d')
        if is_input:
            e('b8', 1)  # MSG_HANDLED: swallow clicks while the minimap is hidden.
        e('c3')
        a.mark('original'); e('619db8', base + native); e('ffe0')
        result = result.ljust(offset - PAGE, b'\x90') + a.finish()
    assert len(result) <= 0x1000
    return result


def validate(game):
    # Verified Radar::newMap store and GameWindow's callback field layout.
    checks = ((NEW_MAP, 0x2A, '8d4e04898630130000'),
              (0xF9A20, 0x16, '8986d8010000'),
              (0xF9A50, 0x16, '8986e0010000'))
    for rva, offset, raw in checks:
        expected = bytes.fromhex(raw)
        if game.read(int(game.base + rva) + offset, len(expected)) != expected:
            raise MemoryReadError('Minimap callback layout is unsupported; restart with a supported stock game.')


def detach(game, region, mailbox):
    address = mailbox + TIMER
    game.replace_pointer(address, game.pointer(address), 0)
    radar = game.pointer(game.base + RADAR)
    window = game.pointer(radar + WINDOW) if radar else 0
    if window:
        for field, native, wrapper in ((INPUT_FIELD, INPUT, INPUT_CODE), (DRAW_FIELD, DRAW, DRAW_CODE)):
            if game.pointer(window + field) == region + wrapper:
                game.replace_pointer(window + field, region + wrapper, game.base + native)
