"""Restore only USA Mission 1's existing Dozer command-bar override.

Layouts verified against the fingerprinted Steam binary. All lookups are bounded;
no allocations, code patches, remote calls, or additions to engine containers.
"""
import struct

from .memory import MemoryReadError

GAME_LOGIC_RVA = 0x639B0C
CONTROL_BAR_RVA = 0x6395F8
COMMAND_SET = "americacommandcentercommandset"
COMMAND_BUTTON = "command_constructamericadozer"
MISSION_MAP = "maps/md_usa01/md_usa01.map"


class DozerUnlock:
    def __init__(self, game):
        self.game = game
        self.changed = False

    def active_logic(self):
        snapshot = self.game.snapshot()
        if snapshot is None or (snapshot.campaign, snapshot.mission, snapshot.map_name) != ("usa", "mission01", MISSION_MAP):
            return None
        logic = self.game.pointer(self.game.base + GAME_LOGIC_RVA)
        # GameLogic::m_gameMode +0x94, GAME_SINGLE_PLAYER == 0.
        if not logic or self.game.pointer(logic + 0x94) != 0:
            return None
        return logic

    def final_override(self, pointer):
        seen = set()
        while pointer:
            if pointer in seen or len(seen) >= 32:
                raise MemoryReadError("Unrecognized command override chain.")
            seen.add(pointer)
            next_pointer = self.game.pointer(pointer + 4)
            if not next_pointer:
                return pointer
            pointer = next_pointer
        return None

    def original_button(self):
        bar = self.game.pointer(self.game.base + CONTROL_BAR_RVA)
        if not bar:
            return None
        command_set = self.game.pointer(bar + 0x2C)
        seen = set()
        while command_set:
            if command_set in seen or len(seen) >= 4096:
                raise MemoryReadError("Unrecognized command-set list.")
            seen.add(command_set)
            if self.game.string(command_set + 0xC) == COMMAND_SET:
                command_set = self.final_override(command_set)
                if self.game.string(command_set + 0xC) != COMMAND_SET:
                    raise MemoryReadError("Command-set override has an unexpected name.")
                button = self.game.pointer(command_set + 0x10)  # slot zero
                button = self.final_override(button)
                if not button or self.game.string(button + 0xC) != COMMAND_BUTTON:
                    raise MemoryReadError("USA Command Center slot 1 is not the stock Dozer command.")
                return button
            command_set = self.game.pointer(command_set + 0x58)
        return None

    def find_slot(self, logic):
        # STLport hash_map: bucket vector start/end at map+4/+8. The map is
        # GameLogic+0x20; node layout is next +0, AsciiString key +4, value +8.
        begin, end = struct.unpack("<II", self.game.read(logic + 0x24, 8))
        if not begin and not end:
            return None
        if not 0 <= end - begin <= 16384 or (end - begin) % 4:
            raise MemoryReadError("Unrecognized command-override table.")
        seen = set()
        for offset in range(0, end - begin, 4):
            node = self.game.pointer(begin + offset)
            chain = set()
            while node:
                if node in chain or len(seen) >= 4096:
                    raise MemoryReadError("Unrecognized command-override bucket chain.")
                chain.add(node)
                seen.add(node)
                if self.game.string(node + 4) == "0" + COMMAND_SET:
                    return node + 8
                node = self.game.pointer(node)
        return None

    def apply(self, unlocked):
        logic = self.active_logic()
        if logic is None:
            self.changed = False
            return "USA Dozer: waiting for USA Mission 1."
        slot = self.find_slot(logic)
        if slot is None:
            return "USA Dozer: waiting for the mission's build restrictions."
        button = self.original_button()
        if button is None:
            return "USA Dozer: waiting for the Command Center build menu."
        current = self.game.pointer(slot)
        if current not in (0, button):
            raise MemoryReadError("Dozer slot contains an unexpected command; left unchanged.")
        desired = button if unlocked else 0
        if current != desired:
            # Recheck the mission and rediscover the node immediately before the
            # write. Never reuse a cached address across loads or mission changes.
            if self.active_logic() != logic or self.find_slot(logic) != slot:
                return "USA Dozer: mission is changing; waiting."
            self.game.replace_pointer(slot, current, desired)
            self.changed = unlocked
        return ("USA Dozer unlocked: reselect your Command Center to build Dozers."
                if unlocked else "USA Dozer locked: waiting for the Archipelago item.")

    def restore(self):
        # Mission reset clears the override table. Only restore if still in the
        # same eligible mission; never write to an old cached allocation.
        if self.changed:
            self.apply(False)
        self.changed = False
