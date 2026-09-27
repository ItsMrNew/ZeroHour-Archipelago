import asyncio
import ctypes as ct
import struct
from types import SimpleNamespace

import pytest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX,
    UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)

from zh.unlock_menu import (build_menu_stub, MANAGER_RVA, TABLE_RVA, ROWS, STRIDE, ROW_DEFS, IDS, UnlockMenu,
    SELECTED_COLOR, AVAILABLE_COLOR, LOCKED_COLOR, PANEL_WIDTH, PANEL_HEIGHT)
from zh.dozer import GAME_LOGIC_RVA
from zh.gameplay import UI_RVA, UI_TABLE_RVA
from zh.memory import CAMPAIGN_GLOBAL_RVA
from zh.mission_data import ALL_BUILDER_ITEMS, BUILDER_ITEMS, CONSUMABLE_CONFIG, BUILDER_CATALOG
from zh.mission_data import select_missions, with_set_bonuses, MISSION_SETS
from zh.unlock_menu import PROGRESS_RED, PROGRESS_ORANGE, PROGRESS_GREEN
from zh.builder_selection import choices
from zh.inventory import Inventory
from zh.state import Progress
from zh.client import ZeroHourClient, IncompatibleRoom
from test_client import Socket
from test_mission_sets import packet


class MenuSimulation:
    base, code, mailbox, manager, logic, ui, campaign = 0x400000, 0x1000000, 0x1002000, 0x2000000, 0x2001000, 0x2002000, 0x2003000
    stack, stop = 0x1108000, 0x1100000

    def __init__(self):
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        for start, size in ((0x400000, 0x700000), (self.code, UnlockMenu.allocation_size), (0x1100000, 0x10000), (self.manager, 0x40000)):
            self.u.mem_map(start, size)
        self.u.mem_write(self.code, build_menu_stub(self.base, self.code, self.mailbox))
        # GadgetButtonSetText calls a system callback, then removes four args.
        self.u.mem_write(self.stop + 0x100, bytes.fromhex('83 c4 10 c3'))
        self.windows, self.destroyed, self.texts = {}, [], {}
        self.next_window = self.manager + 0x4000
        self.original_updates = 0
        self.fail_factory = False
        self.fail_font = False
        self.font_requests = []
        self.original_calls = []
        self.put(self.base + MANAGER_RVA, self.manager)
        self.put(self.manager, self.code + 0x1004)
        self.put(self.base + GAME_LOGIC_RVA, self.logic)
        self.put(self.base + CAMPAIGN_GLOBAL_RVA, self.campaign)
        self.put(self.base + UI_RVA, self.ui)
        self.put(self.ui, self.base + UI_TABLE_RVA)
        self.u.mem_write(self.ui + 13, b'\1')
        self.put(self.campaign + 8, 0x30000)
        self.put(self.campaign + 12, 0x40000)
        self.put(self.mailbox, 1)
        self.put(self.mailbox + 32, 1)
        self.put(self.mailbox + 40, self.logic)
        self.put(self.mailbox + 44, 0x30000)
        self.put(self.mailbox + 48, 0x40000)
        for n, row in enumerate(ROW_DEFS):
            record = self.mailbox + ROWS + n * STRIDE
            self.u.mem_write(record + 4, struct.pack('<7I', *row, 1))
            self.u.mem_write(record + 32, f'Button {row[0]}'.encode() + b'\0')
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def get(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def put(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value))

    def ret(self, argc=0, value=0):
        sp = self.u.reg_read(UC_X86_REG_ESP)
        self.u.reg_write(UC_X86_REG_EAX, value)
        # Native calls may clobber every volatile register.
        self.u.reg_write(UC_X86_REG_ECX, 0xBAD)
        self.u.reg_write(UC_X86_REG_EDX, 0xBAD)
        self.u.reg_write(UC_X86_REG_ESP, sp + 4 + argc * 4)
        self.u.reg_write(UC_X86_REG_EIP, self.get(sp))

    def hook(self, uc, address, size, _):
        sp, this = uc.reg_read(UC_X86_REG_ESP), uc.reg_read(UC_X86_REG_ECX)
        args = lambda n: [self.get(sp + 4 + i * 4) for i in range(n)]
        rva = address - self.base
        if rva == 0xFA2C0:
            assert this == self.manager
            self.original_updates += 1
            self.ret()
        elif rva == 0x2DEED0:
            uc.mem_write(this, bytes(0x1A8)); self.ret(value=this)
        elif rva in (0xFB140, 0xFBED0):
            assert this == self.manager
            is_button = rva == 0xFBED0
            values = args(9 if is_button else 8)
            parent, status, x, y, width, height = values[:6]
            if self.fail_factory:
                self.ret(len(values)); return
            window = self.next_window
            self.next_window += 0x300
            self.windows[window] = {'parent': parent, 'id': self.get(values[6] + 4) if is_button else 0,
                                    'callback': self.base + 0x1AC6B0 if is_button else values[6],
                                    'rect': (x, y, width, height), 'font': values[7] if is_button else None}
            if is_button:
                assert self.get(values[6] + 12) == 0x401
                assert values[7] in (self.manager + 0x1F000, self.manager + 0x1F100)
                assert values[8] == 1
                assert status & 0x4000  # single-line labels
            self.put(window + 4, status)
            uc.mem_write(window + 8, struct.pack('<6I', width, height, x, y, x+width, y+height))
            self.put(window + 0x30, self.windows[window]['id'])
            self.ret(len(values), window)
        elif rva == 0xF99F0:
            self.windows[this]['callback'] = args(1)[0]; self.ret(1)
        elif rva == 0xF9A20:
            self.windows[this]['input'] = args(1)[0]; self.ret(1)
        elif rva in (0xF9270, 0xF9210):
            assert this in self.windows
            flag = args(1)[0]
            assert flag in (0, 1)
            bit = 16 if rva == 0xF9270 else 8
            set_bit = flag if bit == 16 else flag
            self.put(this + 4, (self.get(this + 4) | bit) if set_bit else (self.get(this + 4) & ~bit))
            self.ret(1)
        elif rva == 0x1E00:
            self.put(this, args(1)[0]); self.ret(1, this)
        elif rva == 0x2DF560:
            assert this == self.manager
            name, points, bold = args(3)
            self.font_requests.append((bytes(uc.mem_read(name, 6)), points, bold))
            self.ret(3, 0 if self.fail_font else self.manager + 0x1F000 + bold*0x100)
        elif rva == 0x1FC70:
            self.put(this, self.get(args(1)[0])); self.ret(1, this)
        elif rva == 0x1AC850:
            window, text = args(2)
            assert window in self.windows
            # Match native GGM_SET_LABEL dispatch. Directly setting self.texts
            # masked the toast callback swallowing this message in production.
            uc.mem_write(sp-20, struct.pack('<5I', self.stop+0x100, window, 0x4001, sp+8, 0))
            uc.reg_write(UC_X86_REG_ESP, sp-20)
            uc.reg_write(UC_X86_REG_EIP, self.windows[window]['callback'])
        elif rva == 0x380F60:
            self.put(this, 0); self.ret()
        elif rva == 0xFB290:
            assert this == self.manager
            self.destroyed.append(args(1)[0]); self.ret(1)
        elif rva == 0x1AC6B0:
            values = args(4)
            self.original_calls.append(values)
            if values[1] == 0x4001:
                self.texts[values[0]] = bytes(uc.mem_read(self.get(values[2]),64)).split(b'\0')[0].decode()
            self.ret()
        elif self.base <= address < self.base + 0x700000:
            raise AssertionError(f'Unexpected native call {address:x}')

    def run(self, entry, args=()):
        self.u.reg_write(UC_X86_REG_ESP, self.stack)
        self.u.reg_write(UC_X86_REG_ECX, self.manager)
        self.u.mem_write(self.stack, struct.pack(f'<{1+len(args)}I', self.stop, *args))
        preserved = (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)
        for n, reg in enumerate(preserved): self.u.reg_write(reg, 0xAA00 + n)
        self.u.emu_start(entry, self.stop, count=100000)
        assert self.u.reg_read(UC_X86_REG_ESP) == self.stack + 4
        for n, reg in enumerate(preserved): assert self.u.reg_read(reg) == 0xAA00 + n

    def tick(self):
        self.run(self.code)

    def window(self, ident):
        return next(w for w, value in self.windows.items() if value['id'] == ident)

    def click(self, ident):
        win = self.window(ident)
        owner = self.windows[win]['parent'] or win
        self.run(self.windows[owner]['callback'], (owner, 0x4008, win, 0))


def test_native_menu_creates_windows_labels_and_preserves_update_abi():
    sim = MenuSimulation(); sim.tick()
    assert sim.original_updates == 1
    assert sim.font_requests == [(b'Arial\0', 12, 0), (b'Arial\0', 12, 1)]
    assert len(sim.windows) == len(ROW_DEFS) + 1
    assert sim.get(sim.mailbox + 32) == 0
    assert len(sim.texts) == len(ROW_DEFS)
    assert sim.get(sim.window(1) + 4) & 16 == 0
    assert sim.get(sim.get(sim.mailbox + 28) + 4) & 16
    sim.tick()
    assert len(sim.windows) == len(ROW_DEFS) + 1
    assert sim.original_updates == 2


def test_native_open_tabs_close_and_selection_events():
    sim = MenuSimulation(); sim.tick(); sim.click(1); sim.tick()
    assert not sim.get(sim.get(sim.mailbox + 28) + 4) & 16
    assert not sim.get(sim.window(10) + 4) & 16
    assert sim.get(sim.window(30) + 4) & 16
    sim.click(3); sim.tick()
    assert sim.get(sim.window(10) + 4) & 16
    assert not sim.get(sim.window(30) + 4) & 16
    sim.click(2); sim.tick(); sim.click(10)
    assert sim.get(sim.mailbox + 12) == 10
    sim.click(11)  # event remains latched until Python persists the first choice
    assert sim.get(sim.mailbox + 12) == 10
    sim.click(4); sim.tick()
    assert sim.get(sim.get(sim.mailbox + 28) + 4) & 16


@pytest.mark.parametrize('field', ['loading','save','newgame','mode','intro','victory','mission','campaign','disabled','stale','rewind'])
def test_native_hides_controls_during_transitions_and_outside_play(field):
    sim = MenuSimulation(); sim.tick(); sim.click(1)
    if field in ('loading', 'save', 'newgame'):
        sim.u.mem_write(sim.logic + {'loading':0x51,'save':0x52,'newgame':0x64}[field], b'\1')
    elif field == 'mode': sim.put(sim.logic + 0x94, 2)
    elif field == 'intro': sim.u.mem_write(sim.ui + 13, b'\0')
    elif field == 'victory': sim.u.mem_write(sim.campaign + 16, b'\1')
    elif field == 'mission': sim.put(sim.campaign + 12, 123)
    elif field == 'campaign': sim.put(sim.campaign + 8, 123)
    elif field == 'stale': sim.put(sim.logic + 0x3C, 91)
    elif field == 'rewind': sim.put(sim.mailbox + 52, 91)
    else: sim.put(sim.mailbox, 0)
    sim.tick()
    if field == 'disabled':
        assert sim.get(sim.window(1) + 4) & 16
        assert sim.get(sim.get(sim.mailbox + 28) + 4) & 16
        assert sim.get(sim.mailbox + 16) == 0
    else:
        assert not sim.get(sim.window(1) + 4) & 16
        assert not sim.get(sim.get(sim.mailbox + 28) + 4) & 16
        assert sim.get(sim.mailbox + 20) == 2  # read-only Progress
        assert not sim.get(sim.window(40) + 4) & 16
        for ident in (2,3,10,31):
            assert sim.get(sim.window(ident) + 4) & 16
            sim.click(ident)
            assert sim.get(sim.mailbox + 12) == 0
            assert sim.get(sim.mailbox + 20) == 2
        sim.click(47)
        assert sim.get(sim.mailbox+12) == 47
        sim.put(sim.mailbox+12,0)
        sim.click(46)
        assert sim.get(sim.mailbox+12) == 46
        sim.click(4); sim.tick()
        assert sim.get(sim.get(sim.mailbox+28)+4)&16
        sim.click(1); sim.tick()
        assert not sim.get(sim.get(sim.mailbox+28)+4)&16


@pytest.mark.parametrize('outside', ['main_menu','paused','no_mission'])
def test_preferences_tabs_and_controls_work_without_player_control(outside):
    sim = MenuSimulation()
    if outside == 'main_menu': sim.put(sim.logic+0x94,2)
    elif outside == 'paused': sim.u.mem_write(sim.ui+13,b'\0')
    else: sim.put(sim.base+GAME_LOGIC_RVA,0)
    sim.tick(); sim.click(1); sim.tick()
    for tab, page, events in ((7,3,(51,52,53,54,56,57,58,59,60)),
                              (8,4,(71,72,73,75,76))):
        assert not sim.get(sim.window(tab)+4)&16
        sim.click(tab); sim.tick(); sim.tick()
        assert sim.get(sim.mailbox+20) == page  # not forced back to Progress
        for event in events:
            assert not sim.get(sim.window(event)+4)&16
            sim.put(sim.mailbox+12,0); sim.click(event)
            assert sim.get(sim.mailbox+12) == event
        sim.put(sim.mailbox+12,0)
        for event in (10,31,32,35):
            sim.click(event)
            assert sim.get(sim.mailbox+12) == 0
        sim.click(6); sim.tick()
        assert sim.get(sim.mailbox+20) == 2


def test_tabs_centre_without_gameplay_and_restore_when_returning_to_mission():
    sim = MenuSimulation()
    sim.put(sim.logic+0x94,2)
    sim.tick(); sim.click(1); sim.tick()
    for mode in (2,0,2,0):
        sim.put(sim.logic+0x94,mode)
        sim.tick()
        expected = (178,314,450) if mode == 2 else (284,420,556)
        for ident, x, width in zip((6,7,8),expected,(128,128,132)):
            window = sim.window(ident)
            assert sim.get(window+0x10) == x
            assert sim.get(window+0x18) == x+width
            assert sim.get(window+0x14) == 12
        if mode == 2:
            assert sim.get(sim.window(6)+0x10) + sim.get(sim.window(8)+0x18) == PANEL_WIDTH
        assert sim.get(sim.window(4)+0x10) == 700  # close button stays at the edge
        assert sim.get(sim.mailbox+32) == 0  # no text update required for relocation


def test_native_detach_queues_own_windows_and_restores_original_table():
    sim = MenuSimulation(); sim.tick()
    own_roots = {sim.get(sim.mailbox + 24), sim.get(sim.mailbox + 28), *(sim.window(i) for i in range(80,86))}
    sim.put(sim.mailbox, 2); sim.tick()
    assert set(sim.destroyed) == own_roots
    assert sim.get(sim.manager) == sim.base + TABLE_RVA
    assert sim.get(sim.mailbox) == 3
    # Deferred destroy callback still exists and forwards native button cleanup.
    launcher = sim.window(1)
    sim.run(sim.windows[launcher]['callback'], (launcher, 2, 0, 0))
    assert sim.get(sim.mailbox + 24) == 0
    assert sim.original_calls[-1] == [launcher, 2, 0, 0]


def test_native_destroyed_panel_clears_children_before_recreation():
    sim = MenuSimulation(); sim.tick()
    panel = sim.get(sim.mailbox + 28)
    sim.run(sim.windows[panel]['callback'], (panel, 2, 0, 0))
    assert sim.get(sim.mailbox + 28) == 0
    for n in range(1, len(ROW_DEFS)):
        if ROW_DEFS[n][-1] != 6:
            assert sim.get(sim.mailbox + ROWS + n * STRIDE) == 0
    launcher = sim.get(sim.mailbox + 24)
    sim.tick()
    assert sim.get(sim.mailbox + 28) != panel
    assert sim.get(sim.mailbox + 24) == launcher


def test_native_creation_failure_disables_menu_without_retrying():
    sim = MenuSimulation(); sim.fail_factory = True; sim.tick()
    assert sim.get(sim.mailbox + 56) == 1
    assert sim.get(sim.mailbox) == 0
    sim.tick()
    assert not sim.windows


def test_native_font_failure_does_not_fall_back_to_overlapping_default():
    sim = MenuSimulation(); sim.fail_font = True; sim.tick()
    assert sim.get(sim.mailbox + 56) == 1
    assert not sim.windows


def test_controls_fit_panel_and_visible_rows_do_not_overlap():
    for tab in (1, 2, 3, 4, 5):
        rows = [row for row in ROW_DEFS if row[0] != 1 and row[-1] in (0, tab)]
        for i, (_, x, y, width, height, _) in enumerate(rows):
            assert 0 < x < x + width < PANEL_WIDTH
            assert 0 < y < y + height < PANEL_HEIGHT
            for _, bx, by, bw, bh, _ in rows[i + 1:]:
                assert x + width <= bx or bx + bw <= x or y + height <= by or by + bh <= y


def test_preference_is_per_slot_durable_and_off_is_not_auto_reenabled(tmp_path):
    progress = Progress(tmp_path, 'menu', 0, 1)
    variant = IDS[3]
    progress.choose_builder('usa', variant)
    loaded = Progress(tmp_path, 'menu', 0, 1)
    assert choices(set(IDS), loaded.builder_choices)['usa'] == variant
    assert choices(set(BUILDER_ITEMS), loaded.builder_choices)['usa'] is None
    loaded.choose_builder('usa', None)
    assert choices(set(IDS), Progress(tmp_path, 'menu', 0, 1).builder_choices)['usa'] is None
    assert Progress(tmp_path, 'menu', 0, 2).builder_choices == {}
    with pytest.raises(ValueError): progress.choose_builder('china', variant)


def test_python_inventory_native_click_persistence_and_reconnect(tmp_path, monkeypatch):
    sim = MenuSimulation()
    # Leave creation to the production adapter's label/config publication.
    sim.u.mem_write(sim.mailbox, bytes(0x1000))
    class Game:
        base, pid = sim.base, 123
        def __init__(self):
            self.api = SimpleNamespace(OpenProcess=lambda *args: 1, CloseHandle=lambda *args: True,
                                       WriteProcessMemory=self.write)
        def pointer(self, address): return sim.get(address)
        def read(self, address, count): return bytes(sim.u.mem_read(address, count))
        def replace_pointer(self, address, old, new):
            assert sim.get(address) == old
            sim.put(address, new)
        def write(self, handle, address, buffer, count, written):
            sim.u.mem_write(address, ct.string_at(buffer, count))
            written._obj.value = count
            return True
    progress = Progress(tmp_path, 'native', 0, 1)
    client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
    client.progress, client.death_yaml = progress, (False, 'full_restart', 0)
    client.sets_mode = True
    missions = select_missions()
    locations = {m['id'] for m in with_set_bonuses(missions, 2, 5)}
    adapter = UnlockMenu(Game(), progress, ALL_BUILDER_ITEMS, tracker=(missions, locations), deathlink=client)
    adapter.region, adapter.table, adapter.mailbox, adapter.logic = sim.code, sim.code + 0x1004, sim.mailbox, sim.manager
    state = SimpleNamespace(failed=False, logic=sim.logic, campaign=0x30000, mission=0x40000, frame=0)
    monkeypatch.setattr('zh.unlock_menu.mission_state', lambda game: state)
    inv = Inventory()
    packet = lambda item: {'item': item, 'location': -1, 'player': 1, 'flags': 2}
    inv.apply(0, [packet(item) for item in BUILDER_ITEMS])
    adapter.update(inv); sim.tick()
    assert sim.texts[sim.window(10)] == 'ON: USA Dozer'
    assert sim.texts[sim.window(94)] == '0'
    assert sim.get(sim.window(101)+0x190) == PROGRESS_RED
    assert sim.get(sim.window(92)+0x190) == PROGRESS_RED
    assert sim.get(sim.window(93)+0x190) == sim.get(sim.window(94)+0x190) == PROGRESS_ORANGE
    for ident in (40,41,91,93,95,100):
        assert sim.windows[sim.window(ident)]['font'] == sim.manager+0x1F100
    assert sim.windows[sim.window(101)]['font'] == sim.manager+0x1F000
    inv.apply(len(inv.items), [packet(MISSION_SETS['usa']['item_id'])])
    adapter.update(inv); sim.tick()
    assert sim.texts[sim.window(94)] == '15'
    assert sim.get(sim.window(101)+0x190) == PROGRESS_ORANGE
    progress.completed.add(next(m['id'] for m in missions if m['campaign']=='usa'))
    adapter.update(inv); sim.tick()
    assert sim.texts[sim.window(101)] == 'DONE'
    assert sim.get(sim.window(101)+0x190) == PROGRESS_GREEN
    assert sim.texts[sim.window(94)] == '14'
    def palette(ident, expected):
        # Actual x86 writes: enabled/pressed and hover/hover-pressed must all
        # preserve the selection colour, with readable disabled alternatives.
        window = sim.window(ident)
        for offset in (0x48, 0x54, 0x120, 0x12C):
            assert sim.get(window + offset) == expected
        for offset in (0xB4, 0xC0):
            assert sim.get(window + offset) == LOCKED_COLOR
        assert sim.get(window + 0x190) == 0xFFC4CDD5
    palette(10, SELECTED_COLOR)
    assert sim.texts[sim.window(13)].startswith('Locked:')
    assert not sim.get(sim.window(13) + 4) & 8
    # Even an injected event cannot select an item absent from the inventory.
    sim.put(sim.mailbox + 12, 13); adapter.update(inv)
    assert progress.builder_choices == {}
    inv.apply(len(inv.items), [packet(IDS[3])]); adapter.update(inv); sim.tick()
    assert sim.get(sim.window(13) + 4) & 8
    sim.click(13); adapter.update(inv); sim.tick()
    assert progress.builder_choices['usa'] == IDS[3]
    assert sim.texts[sim.window(13)] == 'ON: Air Force Dozer'
    assert sim.texts[sim.window(10)] == 'OFF: USA Dozer'
    palette(13, SELECTED_COLOR)
    palette(10, AVAILABLE_COLOR)
    assert Progress(tmp_path, 'native', 0, 1).builder_choices == progress.builder_choices
    sim.click(13); adapter.update(inv); sim.tick()
    assert progress.builder_choices['usa'] is None
    palette(13, AVAILABLE_COLOR)
    inv.synchronized = False; adapter.update(inv); sim.tick()
    assert sim.get(sim.window(1) + 4) & 16
    inv.apply(0, [packet(item) for item in BUILDER_ITEMS] + [packet(IDS[3])])
    adapter.update(inv); sim.tick()
    assert sim.texts[sim.window(13)] == 'OFF: Air Force Dozer'
    sim.click(1); sim.click(7); sim.tick()
    sim.click(54); adapter.update(inv); sim.tick()
    assert client.death_link and client.death_link_mode == 'quick_reset'
    palette(54, SELECTED_COLOR)
    assert sim.texts[sim.window(55)].startswith('Active: Quick Reset')
    assert Progress(tmp_path, 'native', 0, 1).deathlink_selection['mode'] == 'quick_reset'
    sim.click(51); adapter.update(inv); sim.tick()
    assert not client.death_link
    palette(51, SELECTED_COLOR)
    sim.click(8); sim.tick(); sim.click(72); adapter.update(inv); sim.tick()
    assert Progress(tmp_path, 'native', 0, 1).notification_settings['scope'] == 'all'
    palette(72, SELECTED_COLOR)
    # Python publishes a newly received toast even when there is no mission.
    monkeypatch.setattr('zh.unlock_menu.mission_state', lambda game: None)
    client.notifications.clock = lambda: 0
    client.notifications.receive({'type':'ItemSend','receiving':3,
        'item':{'player':2,'item':123,'location':100}})
    adapter.update(inv); sim.tick()
    assert sim.texts[sim.window(80)] == 'Player 2 sent'
    assert sim.texts[sim.window(81)] == 'Item 123'
    assert any(call[0] == sim.window(81) and call[1] == 0x4001 for call in sim.original_calls)
    assert not sim.get(sim.window(80)+4)&16
    assert not sim.get(sim.window(1)+4)&16
    assert sim.get(sim.mailbox+20) == 4  # Notifications stays open at the main menu.
    sim.click(73); adapter.update(inv); sim.tick()
    assert client.notifications.settings['scope'] == 'off'
    assert sim.get(sim.window(80)+4)&16
    sim.click(7); sim.tick(); sim.click(54); adapter.update(inv); sim.tick()
    assert client.death_link and client.death_link_mode == 'quick_reset'
    assert Progress(tmp_path, 'native', 0, 1).deathlink_selection['mode'] == 'quick_reset'
    sim.click(6); sim.tick()
    previous_title = sim.texts[sim.window(41)]
    sim.click(47); adapter.update(inv); sim.tick()
    assert sim.texts[sim.window(41)] != previous_title
    sim.click(46); adapter.update(inv); sim.tick()
    assert sim.texts[sim.window(41)] == previous_title
    client.notifications.clock = lambda: 9
    adapter.update(inv); sim.tick()
    assert sim.get(sim.window(80)+4)&16
    adapter.close(); sim.tick()
    assert sim.get(sim.manager) == sim.base + TABLE_RVA


@pytest.mark.parametrize('generals', [False, True])
def test_protocol_ten_menu_and_legacy_consumables(tmp_path, generals):
    async def run():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        sock = Socket()
        await client.handle(sock, {'cmd':'RoomInfo','seed_name':'menu'})
        data = packet()
        data['slot_data'].update(protocol_version=10, consumables=CONSUMABLE_CONFIG,
            builder_menu=True, general_builder_unlocks=generals,
            builder_scope='campaign_and_challenge_command_centers',
            unit_unlocks=list((ALL_BUILDER_ITEMS if generals else BUILDER_ITEMS).values()))
        await client.handle(sock, data)
        assert client.menu_mode and client.consumables_mode and client.sets_mode
        assert len(client.builder_items) == (12 if generals else 3)
        data['slot_data']['unit_unlocks'] = ['not a builder']
        with pytest.raises(IncompatibleRoom): await client.handle(sock, data)
    asyncio.run(run())
