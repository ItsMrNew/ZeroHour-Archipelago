"""Campaign builder menus using existing CommandSet/CommandButton allocations.

Only checked pointer data is written; no allocations or injected engine calls.
The Steam layouts are shared with the live-verified Dozer prototype.
"""
import struct

from .dozer import DozerUnlock, GAME_LOGIC_RVA, CONTROL_BAR_RVA
from .memory import MemoryReadError
from .mission_data import BUILDER_ITEMS, BY_CAMPAIGN_MISSION

BUTTON_NAMES = ('command_constructamericadozer', 'command_constructchinadozer', 'command_constructglaworker')
# Zero-based slots in USA/China/GLA builder order. China trades Rally Point.
MENUS = {
    'americacommandcentercommandset': (0, 2, 10),
    'chinacommandcentercommandset': (10, 0, 12),
    'chinacommandcentercommandsetupgrade': (10, 0, 12),
    'glacommandcentercommandset': (1, 2, 0),
}


class BuilderUnlock(DozerUnlock):
    menu_defs = MENUS
    button_names = BUTTON_NAMES
    mission_lookup = BY_CAMPAIGN_MISSION

    def __init__(self, game):
        super().__init__(game)
        # Keys identify rediscoverable live fields, never just cached addresses.
        self.edits = {}
        self.set_nodes = set()

    def context(self):
        state = self.game.snapshot()
        if state is None:
            return None  # Incoherent sample; wait without writing or cleanup.
        logic = self.game.pointer(self.game.base + GAME_LOGIC_RVA)
        mode = self.game.pointer(logic + 0x94) if logic else None
        mission = self.mission_lookup.get((state.campaign, state.mission))
        eligible = bool(logic and mode == 0 and mission and state.map_name == mission['map'] and not state.victorious)
        return logic, state, eligible

    def named_list(self, head, next_offset, wanted, nodes=None):
        result, seen = {}, set()
        while head:
            if head in seen or len(seen) >= 8192:
                raise MemoryReadError('Unrecognized command list or cycle.')
            seen.add(head)
            name = self.game.string(head + 0xC)
            if name in wanted:
                final, chain = head, set()
                while final:
                    if final in chain or len(chain) >= 32:
                        raise MemoryReadError('Unexpected command override chain.')
                    chain.add(final)
                    if self.game.string(final + 0xC) != name:
                        raise MemoryReadError('Unexpected command override name.')
                    if nodes is not None:
                        nodes.add((name, final))
                    next_override = self.game.pointer(final + 4)
                    if not next_override:
                        break
                    final = next_override
                if name in result:
                    raise MemoryReadError('Duplicate command name.')
                result[name] = final
            head = self.game.pointer(head + next_offset)
        return result

    def menus(self, include_buttons=True):
        self.set_nodes = set()
        bar = self.game.pointer(self.game.base + CONTROL_BAR_RVA)
        if not bar:
            return {}, {}
        sets = self.named_list(self.game.pointer(bar + 0x2C), 0x58, self.menu_defs, self.set_nodes)
        buttons = (self.named_list(self.game.pointer(bar + 0x28), 0x14, (*self.button_names, 'command_setrallypoint'))
                   if include_buttons else {})
        return sets, buttons

    def overrides(self, logic):
        if not logic:
            return {}
        begin, end = struct.unpack('<II', self.game.read(logic + 0x24, 8))
        if not begin and not end:
            return {}
        if not begin or not 0 <= end - begin <= 16384 or (end - begin) % 4:
            raise MemoryReadError('Unrecognized command-override table.')
        result, seen = {}, set()
        for offset in range(0, end - begin, 4):
            node = self.game.pointer(begin + offset)
            while node:
                if node in seen or len(seen) >= 4096:
                    raise MemoryReadError('Unrecognized command-override bucket chain.')
                seen.add(node)
                key = self.game.string(node + 4)
                if key in result:
                    raise MemoryReadError('Duplicate command override key.')
                result[key] = (node + 8, begin)
                node = self.game.pointer(node)
        return result

    def fields(self, logic, sets, overrides):
        result = {}
        for name, slots in self.menu_defs.items():
            if name not in sets:
                continue
            for index, slot in enumerate(slots):
                key = ('set', name, slot, sets[name])
                result[key] = (sets[name] + 0x10 + slot * 4, index)
                override_name = chr(ord('0') + slot) + name
                if override_name in overrides:
                    address, buckets = overrides[override_name]
                    key = ('override', name, slot, logic, buckets, address)
                    result[key] = (address, index)
        return result

    def allowed(self, key, value, buttons):
        # Accept null, the assigned builder, or the slot's known vanilla value.
        _, name, slot, *_ = key
        index = self.menu_defs[name].index(slot)
        names = {BUTTON_NAMES[index]}
        if name.startswith('china') and slot == 12:
            names.add('command_setrallypoint')
        return value == 0 or value in {buttons[n] for n in names if n in buttons}

    def desired_button(self, index, owned, buttons):
        return buttons[BUTTON_NAMES[index]] if tuple(BUILDER_ITEMS)[index] in owned else 0

    def desired_field(self, key, value, index, owned, buttons):
        return self.desired_button(index, owned, buttons)

    def apply(self, owned):
        context = self.context()
        if context is None:
            return 'Builders: mission is changing; waiting.'
        logic, _, eligible = context
        if not eligible:
            self.restore()
            return 'Builders: waiting for a stock campaign mission.'
        sets, buttons = self.menus()
        if not all(n in sets for n in self.menu_defs) or not all(n in buttons for n in self.button_names):
            return 'Builders: waiting for the Command Center menus.'
        overrides = self.overrides(logic)
        fields = self.fields(logic, sets, overrides)
        plan = []
        ids = tuple(BUILDER_ITEMS)
        for key, (address, index) in fields.items():
            value = self.game.pointer(address)
            if not self.allowed(key, value, buttons):
                raise MemoryReadError(f'Unexpected builder menu command in {key[1]} slot {key[2]+1}; unchanged.')
            if key[0] == 'set' and key not in self.edits:
                # Map overrides can clone a base CommandSet after we changed
                # it. Carry the original through that reachable chain even
                # when the clone already contains the desired pointer.
                inherited = next((record for old, record in self.edits.items()
                                  if old[0] == 'set' and old[1:3] == key[1:3]
                                  and (old[1], old[3]) in self.set_nodes
                                  and record[1] == value), None)
                if inherited is not None:
                    self.edits[key] = inherited
            desired = self.desired_field(key, value, index, owned, buttons)
            if value != desired:
                plan.append((key, address, value, desired))
        # Validate every target before the first write. Recheck live allocations
        # on each change so a load cannot leave us writing cached mission nodes.
        for key, address, value, desired in plan:
            if self.context() != context:
                return 'Builders: mission is changing; waiting.'
            fresh_sets, _ = self.menus(include_buttons=False)
            fresh = self.fields(logic, fresh_sets, self.overrides(logic))
            if key not in fresh or fresh[key][0] != address:
                return 'Builders: menus are changing; waiting.'
            original = self.edits.get(key, (value, value))[0]
            # Record first so shutdown can recover even if post-write read fails.
            self.edits[key] = (original, desired)
            self.game.replace_pointer(address, value, desired)
        # Forget freed override nodes; persistent CommandSets remain tracked.
        self.edits = {k: v for k, v in self.edits.items()
                      if k in fields or (k[0] == 'set' and (k[1], k[3]) in self.set_nodes)}
        names = ', '.join(name for item, name in BUILDER_ITEMS.items() if item in owned) or 'none'
        return f'Builders unlocked: {names}. Reselect your Command Center.'

    def restore(self):
        if not self.edits:
            return
        # Read-only discovery may run outside campaign mode solely to restore
        # our persistent menu edits, including on return to the main menu.
        sets, _ = self.menus(include_buttons=False)
        logic = self.game.pointer(self.game.base + GAME_LOGIC_RVA)
        fields = self.fields(logic, sets, self.overrides(logic))
        # A map may introduce a CommandSet override while its original base
        # remains alive. Restore our edits to any reachable chain node too.
        for name, pointer in self.set_nodes:
            for index, slot in enumerate(self.menu_defs[name]):
                fields[('set', name, slot, pointer)] = (pointer + 0x10 + slot * 4, index)
        for key, (original, applied) in list(self.edits.items()):
            if key in fields:
                address = fields[key][0]
                if self.game.pointer(address) == applied and applied != original:
                    self.game.replace_pointer(address, applied, original)
            self.edits.pop(key, None)
