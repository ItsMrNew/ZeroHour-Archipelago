from .deathlink_options import DEFAULT_SELECTION, menu_labels as deathlink_menu_labels
from .game_options import progress_view
"""Native, independently owned Archipelago windows on the game's GUI thread.

No WND/INI overrides or replacement game assets. The WindowManager instance's
update table is cloned; its original update still runs. All window creation,
text changes, callbacks and destruction occur on that same game thread.
"""
import struct
from types import SimpleNamespace

from .power import PowerOutage
from .compatibility import signature_bytes
from .memory import MemoryReadError, CAMPAIGN_GLOBAL_RVA
from .dozer import GAME_LOGIC_RVA
from .gameplay import UI_RVA, UI_TABLE_RVA, input_enabled
from .notifications import ItemNotifications, ITEM_COLOURS
from .deathlink import mission_state
from .builder_selection import choices, FAMILIES
from .mission_data import BUILDER_CATALOG, ABILITY_ITEMS, REVEAL_MINIMAP_ID, CARPET_BOMB_ID, PATRIOT_AIRDROP_ID, EMERGENCY_REPAIR_ID, MISSION_SETS

MANAGER_RVA = 0x639E14
TABLE_RVA = 0x569FEC
TABLE = tuple(int(v, 16) for v in (
    '3a9520 3a9550 21d640 fa2a0 fa2c0 21d640 3a92e0 3a93d0 3a93e0 3a93f0 '
    '3a9400 3a9410 3a9420 3a9430 3a9440 3a9450 3a9460 3a9470 3a9480 3a9490 '
    '3a94a0 3a94b0 3a94a0 3a94c0 3a94d0 3a94e0 3a94f0 3a9500 3a9510 3a93c0 '
    'fa110 fa110 fa120 fb6d0 fb610 fbed0 fc020 fc160 fc2c0 fc3b0 fc610 fcdb0 '
    'fce50 fcff0 fc8b0 fd300 2dbbd0 2db8d0 2dba50 fb140 fb290 fb410 12fb0 '
    'fa610 fa650 fa5a0 fb090 100340 1003f0 1004f0 100610 fa8f0 fa870 4eaba0 '
    'fa7c0 460a0 4cffa0 fb5d0 fa460 fa4a0 fa4e0 fa530 fa740 fa780 fa6e0 '
    'fa690 fa6b0 fa6d0 fb440 fb570 2df2e0 2df320 2df360 2df3a0 2df490 2df3d0 '
    'f2670 2df500 2df520 2df540 2df4c0 2df4d0 1000d0 2df560 1001c0').split())

# Header: run, reserved, reserved, event, opened, tab, launcher, panel,
# label publication (0 idle / 1 pending / 2 in use), font, logic, campaign,
# mission, reserved, native error. Scratch WinInstanceData +0x100 (0x1a8 bytes).
ROWS, STRIDE = 0x300, 96
IDS = tuple(BUILDER_CATALOG)
ORDER = tuple(i for family in FAMILIES for i in IDS if BUILDER_CATALOG[i][1] == family)
# Record: native window, ID, x, y, width, height, group (0 all, 1 builders,
# 2 abilities), flags (bit 0 enabled, bit 1 selected), 64 bytes ASCII text.
# Colours cover both normal/pressed entries and hover, independently of faction.
SELECTED_COLOR, SELECTED_BORDER = 0xFF246B3A, 0xFF79D991
AVAILABLE_COLOR, AVAILABLE_BORDER = 0xFF304B60, 0xFF799BB4
LOCKED_COLOR, LOCKED_BORDER = 0xFF303841, 0xFF596773
BOLD, TEXT_RED, TEXT_ORANGE, TEXT_GREEN = 8, 16, 32, 64
PROGRESS_RED, PROGRESS_ORANGE, PROGRESS_GREEN = 0xFFFF7777, 0xFFFFB347, 0xFF79D991
PANEL_WIDTH, PANEL_HEIGHT = 760, 316
# Native UI owns the decal lifetime, including its normal reset/destructor.
# Mailbox +68/+72/+76 identify only the preview this menu created.
CARPET_CURSOR, PARADROP_CURSOR, REPAIR_CURSOR = 11, 13, 5
CURSOR_SELECTION, CURSOR_OWNED = 120, 124
RADIUS_DECAL, RADIUS_SHADOW, RADIUS_TYPE = 0x1CF4, 0x1CF8, 0x1D00
CURSOR_TEMPLATES = 0x19AC
CARPET_TEMPLATE = CURSOR_TEMPLATES + CARPET_CURSOR * 28
PARADROP_TEMPLATE = CURSOR_TEMPLATES + PARADROP_CURSOR * 28
CARPET_RADIUS_BITS = struct.unpack('<I', struct.pack('<f', 180.0))[0]
PARADROP_RADIUS_BITS = struct.unpack('<I', struct.pack('<f', 50.0))[0]
REPAIR_RADIUS_BITS = struct.unpack('<I', struct.pack('<f', 100.0))[0]
ROW_DEFS = (
    (1, 12, 56, 180, 32, 0),
    (2, 12, 12, 128, 34, 0),
    (3, 148, 12, 128, 34, 0),
    (4, 700, 12, 46, 34, 0),
    (6, 284, 12, 128, 34, 0),
    (7, 420, 12, 128, 34, 0),
    (8, 556, 12, 132, 34, 0),
    (5, 12, 54, 734, 32, 1),
    *((10 + IDS.index(item), 12 + (n // 4) * 248, 98 + (n % 4) * 52, 238, 44, 1)
      for n, item in enumerate(ORDER)),
    (30, 12, 54, 734, 32, 2),
    (31, 12, 94, 362, 40, 2), (32, 12, 146, 362, 40, 2),
    (35, 12, 198, 362, 40, 2), (37, 12, 250, 362, 40, 2),
    (33, 384, 94, 362, 40, 2), (34, 384, 146, 362, 40, 2),
    (36, 384, 198, 362, 40, 2), (38, 384, 250, 362, 40, 2),
)
# Individual labels allow headings and values to use separate fonts/colours.
ROW_DEFS += (
    (40, 12, 54, 86, 30, 3), (90, 98, 54, 94, 30, 3),
    (91, 192, 54, 112, 30, 3), (92, 304, 54, 64, 30, 3),
    (93, 368, 54, 94, 30, 3), (94, 462, 54, 76, 30, 3),
    (95, 538, 54, 68, 30, 3), (96, 606, 54, 140, 30, 3),
    (41, 12, 86, 300, 30, 3), (97, 312, 86, 434, 30, 3),
    *((100+i*2+j, 12+(i%2)*367+j*167, 118+(i//2)*32, 167 if j==0 else 200, 30, 3)
      for i in range(8) for j in range(2)),
    (46, 12, 254, 362, 44, 3), (47, 384, 254, 362, 44, 3))
ROW_DEFS += (
    (50, 12, 54, 734, 32, 4),
    *((ident, 12+(ident-51)*187, 94, 173, 40, 4) for ident in range(51,55)),
    (55, 12, 140, 734, 30, 4),
    *((ident, 12+(ident-56)*248, 178, 238, 38, 4) for ident in range(56,59)),
    (59, 12, 228, 178, 36, 4), (60, 568, 228, 178, 36, 4),
    (61, 200, 228, 358, 36, 4), (62, 12, 274, 734, 30, 4),
)
ROW_DEFS += (
    (70, 12, 54, 734, 32, 5),
    *((ident, 12+(ident-71)*248, 98, 238, 44, 5) for ident in range(71,74)),
    (74, 12, 158, 734, 32, 5), (75, 12, 204, 362, 40, 5), (76, 384, 204, 362, 40, 5),
    (77, 12, 270, 734, 32, 5),
    # Independent, noninteractive windows remain visible when the panel is closed.
    # One compact card per transfer: sender sent / coloured item / to recipient.
    # Root positions are anchored to the current viewport every native update.
    *((80+i, 268, 12+(i//3)*62+(i%3)*18, 360, 18, 6) for i in range(6)),
)
COUNT = len(ROW_DEFS)
TOAST_ROWS = tuple(ROWS+n*STRIDE for n, row in enumerate(ROW_DEFS) if row[-1] == 6)
assert ROWS + COUNT * STRIDE <= 0x3000
SIGNATURES = {
    0xFA2C0: 'e8 6b fc ff ff',       # WindowManager::update
    0xFB140: '53 56 57 8b f9',       # winCreate (thiscall, ret32)
    0xFBED0: '64 a1 00 00 00 00',    # gogoGadgetPushButton (ret36)
    0x2DEED0: '6a ff 68 e8 b9 92 00',  # WinInstanceData ctor
    0xF9270: '8b c1 8a 4c 24 04',    # winHide (ret4)
    0xF9210: '8b 41 04 53',          # winEnable (ret4)
    0xF99F0: '8b 44 24 04 85 c0',    # winSetSystemFunc (ret4)
    0xF9A20: '8b 44 24 04 85 c0',    # winSetInputFunc (ret4)
    0xF9A50: '8b 44 24 04 85 c0',    # winSetDrawFunc (ret4)
    0x36F100: '55 8b ec 81 ec f4 00 00 00',  # W3DView screenToTerrain, ret8
    0x213880: '55 8b ec 83 ec 74 53 8b',  # RadiusDecalTemplate::createRadiusDecal, ret16
    0x213BB0: '56 8b f1 8b 4e 04 85 c9',  # RadiusDecal::clear
    0x10A140: '83 ec 10 56 57 8b f9 8a',  # InGameUI::handleRadiusCursor
    0x10CD00: '56 57 8b f9 8b 0d 14 99',  # InGameUI::setGUICommand, ret4
    0x1AC850: '64 a1 00 00 00 00',   # GadgetButtonSetText, cdecl
    0xFB290: '55 56 8b 74 24 0c',    # winDestroy (thiscall, ret4)
    0x2DF560: '64 a1 00 00 00 00 6a ff 68 b8 ba 92 00',  # winFindFont, ret12
}


class Assembler:
    def __init__(self, origin):
        self.origin, self.data, self.labels, self.fixups = origin, bytearray(), {}, []

    def emit(self, raw, *words):
        self.data.extend(bytes.fromhex(raw))
        for word in words:
            self.data.extend(struct.pack('<I', word & 0xFFFFFFFF))

    def label(self, name):
        self.labels[name] = len(self.data)

    def branch(self, op, name):
        self.emit(op)
        self.fixups.append((len(self.data), name, True))
        self.emit('00000000')

    def address(self, op, name):
        self.emit(op)
        self.fixups.append((len(self.data), name, False))
        self.emit('00000000')

    def finish(self):
        for offset, name, relative in self.fixups:
            value = self.labels[name] - offset - 4 if relative else self.origin + self.labels[name]
            struct.pack_into('<I', self.data, offset, value & 0xFFFFFFFF)
        return bytes(self.data)


def build_menu_stub(base, code, mailbox):
    a = Assembler(code)
    e, j, label = a.emit, a.branch, a.label
    def call(rva):
        e('b8', base + rva); e('ff d0')
    def manager():
        e('8b 0d', base + MANAGER_RVA)
    def hide(offset, value):
        e('8b 4f ' + f'{offset:02x}'); e('85 c9')
        end = 'hide_' + str(len(a.data)); j('0f 84', end)
        e('68', value); call(0xF9270); label(end)

    e('9c 60'); call(0xFA2C0)
    e('bf', mailbox); manager(); e('85 c9'); j('0f 84', 'done')
    e('81 39', code + 0x1004); j('0f 85', 'done')
    e('83 3f 02'); j('0f 84', 'detach')
    e('83 3f 01'); j('0f 85', 'hidden')
    e('c7 87', 128, 0)  # native, freshly validated gameplay availability
    e('83 bf', 132); e('00'); j('0f 85', 'mission_hidden')
    e('a1', base + GAME_LOGIC_RVA); e('85 c0'); j('0f 84', 'mission_hidden')
    e('3b 47 28'); j('0f 85', 'mission_hidden')
    for offset in (0x51, 0x52, 0x64):
        e(f'80 78 {offset:02x} 00'); j('0f 85', 'mission_hidden')
    e('83 b8 94 00 00 00 00'); j('0f 85', 'mission_hidden')
    e('8b 50 3c 2b 57 34 83 fa 5a'); j('0f 87', 'mission_hidden')
    e('a1', base + CAMPAIGN_GLOBAL_RVA); e('85 c0'); j('0f 84', 'mission_hidden')
    e('80 78 10 00'); j('0f 85', 'mission_hidden')
    e('8b 50 08 3b 57 2c'); j('0f 85', 'mission_hidden')
    e('8b 50 0c 3b 57 30'); j('0f 85', 'mission_hidden')
    e('a1', base + UI_RVA); e('85 c0'); j('0f 84', 'mission_hidden')
    e('80 78 0d 00'); j('0f 84', 'mission_hidden')
    e('c7 87', 128, 1); j('e9', 'create_or_refresh')
    # Outside player control, keep Progress and preferences available. Switch
    # away from gameplay tabs only; don't reset an open preferences tab.
    label('mission_hidden'); e('83 7f 14 02'); j('0f 83', 'settings_tab_ready')
    e('c7 47 14', 2); label('settings_tab_ready')
    j('e8', 'cursor_clear'); e('c7 47 3c', 0); hide(64, 1)
    label('create_or_refresh')
    e('83 7f 1c 00'); j('0f 85', 'existing')
    # A fixed font avoids the resolution-scaled default spilling out of our
    # pixel-sized controls. winFindFont owns its by-value AsciiString argument.
    e('6a 00 6a 0c 6a 00 89 e1'); a.address('68', 'font_name'); call(0x1E00)
    manager(); call(0x2DF560); e('85 c0'); j('0f 84', 'create_failed')
    e('89 47 24')
    # Keep a separate bold font for progress headings (mailbox +136).
    e('6a 01 6a 0c 6a 00 89 e1'); a.address('68', 'font_name'); call(0x1E00)
    manager(); call(0x2DF560); e('85 c0'); j('0f 84', 'create_failed')
    e('89 87', 136)
    # Create the panel, then its controls and independent launcher. All callbacks
    # use our own IDs, never intercept the original control bar or power menu.
    e('8d 8f 00 01 00 00'); call(0x2DEED0)
    e('c7 87 0c 01 00 00', 0x401)  # GWS_PUSH_BUTTON | GWS_MOUSE_TRACK
    e('6a 00'); a.address('68', 'system')
    for value in (PANEL_HEIGHT, PANEL_WIDTH, 92, 12, 0x429, 0):
        e('68', value)
    manager(); call(0xFB140); e('85 c0'); j('0f 84', 'create_failed')
    e('89 47 1c c7 40 48', 0xF0182632)  # panel enabled draw color
    e('c7 40 4c', 0xFF5EADC4)           # panel border
    e('8b c8'); a.address('68', 'consume_input'); call(0xF9A20)
    label('create_rows')
    e('be', mailbox + ROWS); e('bb', COUNT)
    label('create_loop')
    e('83 3e 00'); j('0f 85', 'create_next')
    e('8b 46 04 89 87 04 01 00 00')    # instData.id
    e('6a 01 8b 47 24 f6 46 1c 08'); j('0f 84', 'normal_font')
    e('8b 87', 136); label('normal_font'); e('50 8d 87 00 01 00 00 50')
    for offset in (20, 16, 12, 8):
        e(f'ff 76 {offset:02x}')
    e('68', 0x4429)  # no focus, above, enabled, single-line text
    e('83 7e 04 01'); j('0f 85', 'child_parent')
    label('root_parent'); e('6a 00'); j('e9', 'factory')
    label('child_parent'); e('83 7e 18 06'); j('0f 84', 'root_parent'); e('ff 77 1c')
    label('factory'); manager(); call(0xFBED0)
    e('85 c0'); j('0f 84', 'create_failed')
    e('89 06 83 7e 04 01'); j('0f 85', 'check_toast_callback')
    e('89 47 18'); j('e9', 'root_callback')
    label('check_toast_callback'); e('83 7e 18 06'); j('0f 85', 'create_next')
    label('root_callback'); e('8b c8'); a.address('68', 'system'); call(0xF99F0)
    label('create_next'); e('83 c6 60 4b'); j('0f 85', 'create_loop')
    e('c7 47 20', 1)
    label('existing')
    for offset in TOAST_ROWS:
        e('83 bf', offset); e('00'); j('0f 84', 'create_rows')
    e('83 bf', 128); e('00'); j('0f 84', 'show_panel')
    j('e8', 'target_sync')
    label('show_panel')
    hide(24, 0)
    e('8b 4f 1c 8b 47 10 83 f0 01 50'); call(0xF9270)
    label('publish_labels')
    # Claimed labels cannot be overwritten by Python while Unicode strings are
    # being copied. Window pointers are written exclusively by this GUI thread.
    e('b8', 1); e('ba', 2); e('f0 0f b1 57 20')
    e('0f 94 c0 0f b6 e8')  # EBP = refresh labels this frame
    e('be', mailbox + ROWS); e('bb', COUNT)
    label('refresh_loop')
    e('8b 0e 85 c9'); j('0f 84', 'refresh_next')
    # GameWindow's own root region (lo.x +0x10, hi.x +0x18). No children or
    # cached text layout depend on a position-only change. Use the same verified
    # W3DView dimensions as terrain targeting, including its screen origin.
    e('83 7e 18 06'); j('0f 85', 'toast_position_ready')
    e('a1', base + 0x639598); e('85 c0'); j('0f 84', 'toast_position_ready')
    e('81 38', base + 0x568B58); j('0f 85', 'toast_position_ready')
    e('8b 50 18 81 fa', 640); j('0f 82', 'toast_position_ready')
    e('81 fa', 16384); j('0f 87', 'toast_position_ready')
    e('03 50 20 83 ea 0c 89 51 18 2b 56 10 89 51 10')
    label('toast_position_ready')
    # Centre the three remaining tabs as a group when gameplay tabs are hidden.
    # Restore their original positions on returning to play, even when no label
    # publication is pending. Child regions are relative to their parent panel.
    e('8b 46 04 83 f8 06'); j('0f 82', 'tab_position_ready')
    e('83 f8 08'); j('0f 87', 'tab_position_ready')
    e('8b 56 08 83 bf', 128); e('00'); j('0f 85', 'tab_position_apply')
    e('83 ea 6a')  # 284 -> 178; group width 404 centred inside the 760px panel.
    label('tab_position_apply'); e('89 51 10 03 56 10 89 51 18')
    label('tab_position_ready')
    e('83 7e 18 06'); j('0f 84', 'row_visible')
    e('8b 46 18 85 c0'); j('0f 84', 'row_visible')
    e('48 3b 47 14 0f 95 c0 0f b6 c0'); j('e9', 'row_hide')
    label('row_visible'); e('33 c0')
    label('row_hide')
    e('83 bf', 128); e('00'); j('0f 85', 'check_hidden_flag')
    for ident in (2, 3):
        e(f'83 7e 04 {ident:02x}'); j('0f 84', 'hide_action_tab')
    j('e9', 'check_hidden_flag')
    label('hide_action_tab'); e('b8', 1)
    label('check_hidden_flag'); e('f6 46 1c 04'); j('0f 84', 'not_hidden_flag'); e('b8', 1); label('not_hidden_flag'); e('50'); call(0xF9270)
    e('85 ed'); j('0f 84', 'refresh_next')
    e('8b 0e 8b 46 1c 83 e0 01 50'); call(0xF9210)
    # These are our own windows. Set all native push-button draw states on the
    # GUI thread, so mouse hover/press cannot turn an active choice red/yellow.
    e('8b 0e b8', AVAILABLE_COLOR); e('ba', AVAILABLE_BORDER)
    e('f6 46 1c 02'); j('0f 84', 'palette')
    e('b8', SELECTED_COLOR); e('ba', SELECTED_BORDER)
    label('palette')
    for offset in (0x48, 0x54, 0x120, 0x12C):
        e('89 81', offset); e('89 91', offset + 4)
    for offset in (0xB4, 0xC0):
        e('c7 81', offset, LOCKED_COLOR); e('c7 81', offset + 4, LOCKED_BORDER)
    for offset in (0x188, 0x190, 0x198):
        e('c7 81', offset, 0xFFF3F6F8 if offset != 0x190 else 0xFFC4CDD5)
        e('c7 81', offset + 4, 0xFF101820)
    e('83 7e 18 06'); j('0f 85', 'normal_palette')
    # Disabled push-button roots are noninteractive. Matching fill/border joins
    # the three text lines into one quiet card without button-like separators.
    for offset in (0xB4, 0xB8, 0xC0, 0xC4):
        e('c7 81', offset, 0xFF101820)
    e('c7 81', 0x190, 0xFFF3F6F8)
    label('normal_palette')
    for mask, style, color in ITEM_COLOURS:
        e('f7 46 1c', style); j('0f 84', 'item_color_next_'+str(style))
        e('b8', color); j('e9', 'status_color')
        label('item_color_next_'+str(style))
    e('f6 46 1c 10'); j('0f 84', 'not_red'); e('b8', PROGRESS_RED); j('e9', 'status_color')
    label('not_red'); e('f6 46 1c 20'); j('0f 84', 'not_orange'); e('b8', PROGRESS_ORANGE); j('e9', 'status_color')
    label('not_orange'); e('f6 46 1c 40'); j('0f 84', 'text_ready'); e('b8', PROGRESS_GREEN)
    label('status_color')
    for offset in (0x188, 0x190, 0x198):
        e('89 81', offset)
    label('text_ready')
    # Owned AsciiString followed by owned UnicodeString, matching native ABI.
    e('6a 00 89 e1 8d 46 20 50'); call(0x1E00)
    e('6a 00 89 e1 8d 44 24 04 50'); call(0x1FC70)
    e('ff 36'); call(0x1AC850); e('83 c4 08')
    e('89 e1'); call(0x380F60); e('83 c4 04')
    label('refresh_next'); e('83 c6 60 4b'); j('0f 85', 'refresh_loop')
    e('85 ed'); j('0f 84', 'done')
    e('c7 47 20', 0); j('e9', 'done')
    label('hidden'); e('c7 47 10', 0)
    j('e8', 'cursor_clear')
    e('c7 47 3c', 0); hide(64, 1)
    for offset in TOAST_ROWS:
        e('8b 8f', offset); e('85 c9'); j('0f 84', 'hidden_toast_'+str(offset))
        e('6a 01'); call(0xF9270); label('hidden_toast_'+str(offset))
    hide(24, 1); hide(28, 1); j('e9', 'done')
    label('create_failed'); e('c7 47 38', 1); e('c7 07', 0); j('e9', 'hidden')
    label('detach')
    j('e8', 'cursor_clear')
    for offset in TOAST_ROWS:
        e('8b 87', offset); e('85 c0'); j('0f 84', 'destroy_toast_'+str(offset))
        e('50'); manager(); call(0xFB290); label('destroy_toast_'+str(offset))
    for offset in (64, 28, 24):
        e(f'8b 47 {offset:02x} 85 c0'); end = f'destroy_{offset}'
        j('0f 84', end); e('50'); manager(); call(0xFB290); label(end)
    manager(); e('c7 01', base + TABLE_RVA); e('c7 07', 3)
    label('done'); e('61 9d c3')

    label('system')
    e('60 bf', mailbox)
    e('8b 44 24 24 8b 54 24 28')  # window, message after pushad
    e('83 fa 02'); j('0f 84', 'destroy_notice')
    e('81 fa', 0x4008); j('0f 85', 'pass_system')
    e('83 3f 01'); j('0f 85', 'handled')
    e('8b 54 24 2c 85 d2'); j('0f 84', 'handled')
    e('8b 52 30')  # selected control's WinInstanceData ID
    # Tracker navigation and local preferences are safe without a mission.
    # Gameplay events still require freshly validated player control.
    for ident, target in ((1, 'toggle'), (4, 'close_panel'), (6, 'progress_tab'),
                          (7, 'deathlink_tab'), (8, 'notifications_tab'),
                          (46, 'queue_event'), (47, 'queue_event')):
        e('83 fa ' + f'{ident:02x}'); j('0f 84', target)
    for ident in (51, 52, 53, 54, 56, 57, 58, 59, 60, 71, 72, 73, 75, 76):
        e(f'83 fa {ident:02x}'); j('0f 84', 'queue_event')
    e('83 bf', 128); e('00'); j('0f 84', 'handled')
    for ident, target in ((2, 'builders_tab'), (3, 'abilities_tab')):
        e('83 fa ' + f'{ident:02x}'); j('0f 84', target)
    e('83 fa 1f'); j('0f 84', 'queue_event')
    e('83 fa 20'); j('0f 84', 'queue_event')
    e('83 fa 23'); j('0f 84', 'queue_event')
    e('83 fa 25'); j('0f 84', 'queue_event')
    e('83 fa 0a'); j('0f 82', 'handled')
    e('83 fa 15'); j('0f 87', 'handled')
    label('queue_event'); e('33 c0 f0 0f b1 57 0c'); j('e9', 'handled')
    label('toggle'); e('c7 47 3c', 0); j('e8', 'cursor_clear'); e('83 77 10 01'); j('e9', 'handled')
    label('builders_tab'); e('c7 47 14', 0); j('e9', 'handled')
    label('abilities_tab'); e('c7 47 14', 1); j('e9', 'handled')
    label('deathlink_tab'); e('c7 47 14', 3); j('e9', 'handled')
    label('notifications_tab'); e('c7 47 14', 4); j('e9', 'handled')
    label('progress_tab'); e('c7 47 14', 2); j('e9', 'handled')
    label('close_panel'); e('c7 47 10', 0); j('e9', 'handled')
    label('destroy_notice')
    for offset in TOAST_ROWS:
        e('3b 87', offset); j('0f 85', 'next_toast_'+str(offset))
        e('c7 87', offset, 0); j('e9', 'forward'); label('next_toast_'+str(offset))
    e('3b 47 40'); j('0f 85', 'destroy_panel')
    j('e8', 'cursor_clear')
    e('c7 47 40', 0); e('c7 47 3c', 0); j('e9', 'handled')
    label('destroy_panel')
    e('3b 47 1c'); j('0f 85', 'destroy_launcher')
    e('c7 47 1c', 0)
    # Toasts are independent roots; destroying the panel must not orphan them.
    e('be', mailbox+ROWS+STRIDE); e('bb', COUNT-1)
    label('clear_children'); e('83 7e 18 06'); j('0f 84', 'skip_clear_child')
    e('c7 06', 0); label('skip_clear_child'); e('83 c6 60 4b'); j('0f 85', 'clear_children')
    j('e9', 'handled')
    label('destroy_launcher'); e('3b 47 18'); j('0f 85', 'handled')
    e('c7 47 18', 0); e('c7 87', ROWS, 0); j('e9', 'forward')
    label('pass_system'); e('3b 47 18'); j('0f 84', 'forward')
    # GGM_SET_LABEL must reach the original push-button handler on root toasts.
    # Only our panel consumes unrelated messages; it has no gadget text state.
    for offset in TOAST_ROWS:
        e('3b 87', offset); j('0f 84', 'forward')
    label('handled'); e('61 b8', 1); e('c3')
    label('forward'); e('61 b8', base + 0x1AC6B0); e('ff e0')
    label('consume_input'); e('b8', 1); e('c3')
    # Transparent terrain-only mouse catcher. Above-layer HUD/menu windows
    # retain their normal input; conversion and window APIs stay on GUI thread.
    label('target_sync')
    e('60 83 7f 3c 01'); j('0f 85', 'target_hide')
    e('8b 35', base + 0x639598); e('85 f6'); j('0f 84', 'target_cancel')
    e('81 3e', base + 0x568B58); j('0f 85', 'target_cancel')
    e('83 7f 40 00'); j('0f 85', 'target_show')
    e('6a 00'); a.address('68', 'system')
    for off in (0x1C, 0x18, 0x24, 0x20):
        e(f'ff 76 {off:02x}')
    e('68', 0x409); e('6a 00'); manager(); call(0xFB140)
    e('85 c0'); j('0f 84', 'target_cancel')
    e('89 47 40 8b c8'); a.address('68', 'target_input'); call(0xF9A20)
    e('8b 4f 40'); a.address('68', 'target_draw'); call(0xF9A50)
    label('target_show'); j('e8', 'cursor_sync')
    e('83 7f 3c 01'); j('0f 85', 'target_hide')
    hide(64, 0); j('e9', 'target_end')
    label('target_cancel'); e('c7 47 3c', 3)
    label('target_hide'); j('e8', 'cursor_clear'); hide(64, 1)
    label('target_end'); e('61 c3')
    label('target_draw'); e('31 c0 c3')
    label('target_input')
    e('60 bf', mailbox)
    e('83 3f 01'); j('0f 85', 'target_input_done')
    e('83 7f 3c 01'); j('0f 85', 'target_input_done')
    e('8b 44 24 28 83 f8 0e'); j('0f 84', 'target_input_cancel')
    e('83 f8 06'); j('0f 85', 'target_input_done')
    e('8b 35', base + 0x639598); e('85 f6'); j('0f 84', 'target_input_cancel')
    e('81 3e', base + 0x568B58); j('0f 85', 'target_input_cancel')
    e('8b 44 24 2c 0f b7 d0 c1 e8 10')
    e('89 57 50 89 47 54')
    # Bounds in screen pixels; reject HUD clicks and stale resolution geometry.
    e('2b 56 20 2b 46 24 3b 56 18'); j('0f 83', 'target_input_done')
    e('3b 46 1c'); j('0f 83', 'target_input_done')
    e('68', mailbox + 88); e('68', mailbox + 80); e('89 f1'); call(0x36F100)
    e('c7 47 3c', 2); j('e8', 'cursor_clear'); j('e9', 'target_input_done')
    label('target_input_cancel'); e('c7 47 3c', 3); j('e8', 'cursor_clear')
    label('target_input_done'); e('61 b8', 1); e('c3')
    # Use the selected stock CarpetBomb or Paradrop decal and native updater.
    # setRadiusCursor normally requires a selected drawable or native power
    # source; AP abilities need neither. The UI still owns/resets the decal.
    label('cursor_sync'); e('60')
    e('8b 6f 78 83 fd 0b'); j('0f 84', 'cursor_kind_ok')
    e('83 fd 0d'); j('0f 84', 'cursor_kind_ok')
    e('83 fd 05'); j('0f 85', 'cursor_cancel')
    label('cursor_kind_ok')
    e('8b 35', base + UI_RVA); e('85 f6'); j('0f 84', 'cursor_cancel')
    e('81 3e', base + UI_TABLE_RVA); j('0f 85', 'cursor_cancel')
    for rva in (0x637A80, 0x639B00, 0x6381BC):  # Mouse, Radar, GlobalData
        e('a1', base + rva); e('85 c0'); j('0f 84', 'cursor_cancel')
    e('a1', base + 0x6395A0); e('85 c0'); j('0f 84', 'cursor_cancel')
    e('8b 58 0c 85 db'); j('0f 84', 'cursor_cancel')
    e('83 7f 44 00'); j('0f 84', 'cursor_enter')
    e('3b 77 44'); j('0f 85', 'cursor_cancel')
    e('3b 5f 4c'); j('0f 85', 'cursor_cancel')
    e('83 be 3c 14 00 00 00'); j('0f 85', 'cursor_cancel')
    # Normal engine clearing can be followed by a fresh preview. A foreign
    # command/cursor takes precedence; never clear or overwrite its decal.
    e('83 be', RADIUS_TYPE); e('00'); j('0f 85', 'cursor_owned')
    e('83 be', RADIUS_SHADOW); e('00'); j('0f 84', 'cursor_create')
    j('e9', 'cursor_cancel')
    label('cursor_owned')
    e('8b 47 7c 3b c5'); j('0f 85', 'cursor_cancel')
    e('39 86', RADIUS_TYPE); j('0f 85', 'cursor_cancel')
    e('8b 86', RADIUS_SHADOW); e('85 c0'); j('0f 84', 'cursor_cancel')
    e('3b 47 48'); j('0f 85', 'cursor_cancel')
    j('e9', 'cursor_update')
    label('cursor_enter')
    # Selecting our power replaces any previous pending world command once.
    e('6a 00 89 f1'); call(0x10CD00)
    e('89 77 44 89 5f 4c')
    label('cursor_create')
    e('8d 86', RADIUS_DECAL); e('50 53 b8', CARPET_RADIUS_BITS)
    e('83 fd 05'); j('0f 85', 'cursor_not_repair')
    e('b8', REPAIR_RADIUS_BITS); j('e9', 'cursor_radius_ready')
    label('cursor_not_repair')
    e('83 fd 0d'); j('0f 85', 'cursor_radius_ready')
    e('b8', PARADROP_RADIUS_BITS)
    label('cursor_radius_ready'); e('50')
    e('68', mailbox + 104); e('6b d5 1c 8d 8c 16', CURSOR_TEMPLATES); call(0x213880)
    e('8b 86', RADIUS_SHADOW); e('85 c0'); j('0f 84', 'cursor_create_failed')
    e('89 47 48 89 6f 7c 89 ae', RADIUS_TYPE)
    label('cursor_update'); e('89 f1'); call(0x10A140); j('e9', 'cursor_done')
    label('cursor_create_failed'); e('8d 8e', RADIUS_DECAL); call(0x213BB0)
    label('cursor_cancel'); e('c7 47 3c', 3); j('e8', 'cursor_clear')
    label('cursor_done'); e('61 c3')
    label('cursor_clear'); e('60 8b 77 44 85 f6'); j('0f 84', 'cursor_clear_done')
    e('3b 35', base + UI_RVA); j('0f 85', 'cursor_forget')
    e('81 3e', base + UI_TABLE_RVA); j('0f 85', 'cursor_forget')
    e('83 be 3c 14 00 00 00'); j('0f 85', 'cursor_forget')
    e('8b 47 7c 39 86', RADIUS_TYPE); j('0f 85', 'cursor_forget')
    e('8b 47 48 85 c0'); j('0f 84', 'cursor_forget')
    e('3b 86', RADIUS_SHADOW); j('0f 85', 'cursor_forget')
    e('8d 8e', RADIUS_DECAL); call(0x213BB0)
    e('c7 86', RADIUS_TYPE, 0)
    label('cursor_forget'); e('c7 47 7c', 0); e('c7 47 44', 0); e('c7 47 48', 0); e('c7 47 4c', 0)
    label('cursor_clear_done'); e('61 c3')
    label('font_name'); a.data.extend(b'Arial\0')
    result = a.finish()
    if len(result) > 0x1000:
        raise ValueError('Native menu exceeds its executable page')
    return result


class UnlockMenu(PowerOutage):
    radar_outage_enabled = False  # This hook owns UI controls, not gameplay effects.
    allocation_size = 0x5000  # code, vtable, then three writable control-data pages
    layouts = {TABLE_RVA: TABLE}
    signature = (0xFA2C0, bytes.fromhex(SIGNATURES[0xFA2C0]))

    def __init__(self, game, progress, enabled_items, abilities=None, tracker=None, deathlink=None):
        super().__init__(game)
        self.tracker, self.tracker_page = tracker, 0
        self.deathlink = deathlink
        self.notifications = deathlink.notifications if deathlink else ItemNotifications()
        self.progress = progress
        self.enabled_items = set(enabled_items)
        self.last_labels = None
        self.initialized = False
        self.abilities = abilities
        self.target_item = None

    def make_stub(self, code, mailbox):
        for rva, raw in SIGNATURES.items():
            expected = bytes.fromhex(raw)
            if self.game.read(self.game.base + rva, len(expected)) != signature_bytes(self.game.base, expected, rva):
                raise MemoryReadError('Archipelago menu: unsupported native window function.')
        return build_menu_stub(self.game.base, code, mailbox)

    def put(self, offset, value):
        address = self.mailbox + offset
        old = self.game.pointer(address)
        if old != value:
            self.game.replace_pointer(address, old, value)

    def suspend(self):
        self.target_item = None
        if self.abilities:
            self.abilities.suspend()
        if self.mailbox:
            self.put(0, 0)
            self.put(60, 0)

    def update(self, inventory, settings_only=False):
        state = mission_state(self.game)
        if not inventory.synchronized:
            self.suspend()
            return
        playable = bool(state and not state.failed and not settings_only and input_enabled(self.game))
        manager = self.game.pointer(self.game.base + MANAGER_RVA)
        if not manager:
            return
        self.install(SimpleNamespace(logic=manager))
        if self.abilities and playable:
            self.abilities.tick()
            target_state = self.game.pointer(self.mailbox + 60)
            if target_state == 2:
                target = struct.unpack('<3f', self.game.read(self.mailbox + 88, 12))
                self.put(60, 0)
                item, self.target_item = self.target_item, None
                if item is not None:
                    self.abilities.cast(item, inventory, target)
            elif target_state in (0, 3) or self.abilities.state is None:
                self.target_item = None
                self.put(60, 0)
        elif self.abilities:
            self.abilities.suspend()
            self.target_item = None
            self.put(60, 0)
        if self.game.pointer(self.mailbox + 56):
            raise MemoryReadError('Archipelago menu could not create native controls; restart Zero Hour.')
        owned = {item for item in self.enabled_items if inventory.count(item)}
        selected = choices(owned, self.progress.builder_choices)
        event = self.game.pointer(self.mailbox + 12)
        if event:
            if event in (71, 72, 73, 75, 76) and self.deathlink:
                self.deathlink.notification_event(event)
            if event in (51, 52, 53, 54, 56, 57, 58, 59, 60) and self.deathlink:
                self.deathlink.deathlink_event(event)
            if event in (46, 47):
                self.tracker_page += 1 if event == 47 else -1
            if playable and 10 <= event < 10 + len(IDS) and IDS[event - 10] in owned:
                item = IDS[event - 10]
                family = BUILDER_CATALOG[item][1]
                self.progress.choose_builder(family, None if selected[family] == item else item)
                selected = choices(owned, self.progress.builder_choices)
            elif playable and self.abilities and event == 31:
                if self.abilities.cast(REVEAL_MINIMAP_ID, inventory):
                    self.put(16, 0)
            elif playable and self.abilities and event in (32, 35, 37):
                item = {32: CARPET_BOMB_ID, 35: PATRIOT_AIRDROP_ID, 37: EMERGENCY_REPAIR_ID}[event]
                if self.abilities.ready(item, inventory):
                    self.target_item = item
                    self.put(CURSOR_SELECTION, {CARPET_BOMB_ID: CARPET_CURSOR, PATRIOT_AIRDROP_ID: PARADROP_CURSOR, EMERGENCY_REPAIR_ID: REPAIR_CURSOR}[item])
                    self.put(16, 0)
                    self.put(60, 1)
            self.put(12, 0)
        labels = {1: ('Archipelago', True), 2: ('Builders', True), 3: ('Abilities', True),
                  4: ('X', True), 5: ('One per faction. Turn OFF to restore native CC builders.', False),
                  30: ('Select an ability. Click terrain to target; right-click cancels.', False),
                  33: ('15 seconds of vision. 3-minute cooldown.', False),
                  34: ('Target a strike. 4-minute cooldown.', False),
                  36: ('3 self-powered Patriots. 5-min cooldown.', False),
                  38: ('Cooldown: 4:00', False)}
        deathlink = getattr(self, 'deathlink', None)
        notifications = getattr(self, 'notifications', None)
        labels.update((notifications or ItemNotifications()).labels())
        if not deathlink:
            labels[8] = ('Notifications', 4)
        labels.update(deathlink.deathlink_labels() if deathlink else deathlink_menu_labels(DEFAULT_SELECTION, (False, 'full_restart', 0), 0))
        if not deathlink:
            labels[7] = ('DeathLink', 4)
        tracker = getattr(self, 'tracker', None)
        labels[6] = ('Progress', 1 if tracker else 4)
        unlocked = {key for key, definition in MISSION_SETS.items() if inventory.count(definition['item_id'])}
        if deathlink and not deathlink.sets_mode:
            unlocked = set(MISSION_SETS)  # Older rooms without mission-set locks.
        view = progress_view(tracker[0], self.progress.completed, tracker[1], self.tracker_page, unlocked) if tracker else None
        labels.update({40: ('Checks:', BOLD), 90: (f'{view["earned"]}/{view["total"]}' if view else '', 0),
                       91: ('Remaining:', BOLD|TEXT_RED), 92: (str(view['remaining']) if view else '', TEXT_RED),
                       93: ('In Logic:', BOLD|TEXT_ORANGE), 94: (str(view['in_logic']) if view else '', TEXT_ORANGE),
                       95: ('Sets:', BOLD), 96: (f'{view["done_sets"]}/{view["total_sets"]}' if view else '', 0),
                       41: (view['title'] if view else '', BOLD), 97: (view['set_progress'] if view else '', 0)})
        for i in range(8):
            mission = view['missions'][i] if view and i < len(view['missions']) else None
            labels[100+i*2] = (mission[0], BOLD) if mission else ('', 4|BOLD)
            labels[101+i*2] = (mission[1], {'complete': TEXT_GREEN, 'available': TEXT_ORANGE, 'locked': TEXT_RED}[mission[2]]) if mission else ('', 4)
        labels[46], labels[47] = ('Previous set', 1), ('Next set', 1)
        if self.abilities:
            for row, item in ((33, REVEAL_MINIMAP_ID), (34, CARPET_BOMB_ID), (36, PATRIOT_AIRDROP_ID), (38, EMERGENCY_REPAIR_ID)):
                seconds = self.abilities.cooldown(item) // 30
                labels[row] = (f'Cooldown: {seconds // 60}:{seconds % 60:02}', 0)
        for ident, item in ((31, REVEAL_MINIMAP_ID), (32, CARPET_BOMB_ID), (35, PATRIOT_AIRDROP_ID), (37, EMERGENCY_REPAIR_ID)):
            labels[ident] = (self.abilities.label(item, inventory) if self.abilities
                             else ('N/A: ' + ABILITY_ITEMS[item], 0))
        if self.game.pointer(self.mailbox + 60) == 1:
            labels[1] = ('Cancel targeting', True)
        for n, item in enumerate(IDS):
            name, family, _ = BUILDER_CATALOG[item]
            state_text = ('N/A' if item not in self.enabled_items else 'Locked' if item not in owned
                          else 'ON' if selected[family] == item else 'OFF')
            # Full item names in the console/YAML; shorter labels fit native buttons.
            short_name = name if item in IDS[:3] else name.split(' ', 1)[1]
            flags = int(item in owned) | (2 if selected[family] == item else 0)
            labels[10 + n] = (f'{state_text}: {short_name}', flags)
        if self.game.pointer(self.mailbox + 32) == 0 and labels != self.last_labels:
            handle = self.game.api.OpenProcess(0x1038, False, self.game.pid)
            if not handle:
                raise MemoryReadError('Archipelago menu: could not update labels.')
            try:
                for n, (ident, x, y, width, height, group) in enumerate(ROW_DEFS):
                    text, enabled = labels[ident]
                    if not self.initialized:
                        self._write(handle, self.mailbox + ROWS + n * STRIDE + 4,
                                    struct.pack('<6I', ident, x, y, width, height, group))
                    payload = struct.pack('<I', int(enabled)) + text.encode('ascii')[:63].ljust(64, b'\0')
                    self._write(handle, self.mailbox + ROWS + n * STRIDE + 28, payload)
                self.initialized = True
                self.last_labels = labels
                self.put(32, 1)
            finally:
                self.game.api.CloseHandle(handle)
        for offset, value in ((40, state.logic if state else 0), (44, state.campaign if state else 0),
                              (48, state.mission if state else 0), (52, state.frame if state else 0),
                              (132, int(not playable))):
            self.put(offset, value)
        self.put(0, 1)

    def close(self):
        # The GUI thread destroys its windows and restores its own vtable. Never
        # free published callbacks: deferred GWM_DESTROY messages still use them.
        if self.abilities:
            self.abilities.suspend()
        if self.mailbox:
            self.put(0, 2)
