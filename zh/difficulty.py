"""Read the loaded campaign difficulty and the active script-engine difficulty."""
import argparse
import struct

from .memory import GameMemory, MemoryReadError, CAMPAIGN_GLOBAL_RVA, CAMPAIGN_VTABLE_RVA
from .mission_data import ALL_BY_CAMPAIGN_MISSION

GAME_LOGIC_RVA = 0x639B0C
SCRIPT_ENGINE_RVA = 0x639580
SCRIPT_VTABLE_RVA = 0x545D08
DIFFICULTY_NAMES = ('Easy', 'Medium', 'Hard')
# Steam CampaignManager::xfer at RVA 0x118c09 transfers manager+0x18.
# Native Restart Mission reads ScriptEngine+0x10db8 at RVA 0x1cb30b,
# then passes it as the difficulty argument to MSG_NEW_GAME.
CAMPAIGN_DIFFICULTY_OFFSET = 0x18
SCRIPT_DIFFICULTY_OFFSET = 0x10DB8


def inspect_difficulty(game):
    logic = game.pointer(game.base + GAME_LOGIC_RVA)
    if not logic or game.pointer(logic + 0x94) != 0:
        raise MemoryReadError('Load a story or Generals Challenge mission first.')
    loading = game.read(logic + 0x51, 2)
    quitting = game.read(logic + 0x64, 1)
    if any(loading) or any(quitting) or game.pointer(logic + 0x3C) < 1:
        raise MemoryReadError('Mission is loading or exiting. Wait and check again.')
    manager = game.pointer(game.base + CAMPAIGN_GLOBAL_RVA)
    scripts = game.pointer(game.base + SCRIPT_ENGINE_RVA)
    if (not manager or not scripts
            or game.pointer(manager) != game.base + CAMPAIGN_VTABLE_RVA
            or game.pointer(scripts) != game.base + SCRIPT_VTABLE_RVA):
        raise MemoryReadError('Difficulty layout does not match the supported Steam game.')
    before = game.read(manager + 8, 20)
    snapshot = game.snapshot()
    mission = ALL_BY_CAMPAIGN_MISSION.get((snapshot.campaign, snapshot.mission)) if snapshot else None
    if not mission or snapshot.map_name != mission['map']:
        raise MemoryReadError('No supported campaign mission is loaded. Load a save and try again.')
    campaign = struct.unpack('<i', before[CAMPAIGN_DIFFICULTY_OFFSET - 8:])[0]
    active = struct.unpack('<i', game.read(scripts + SCRIPT_DIFFICULTY_OFFSET, 4))[0]
    if campaign not in range(3) or active not in range(3):
        raise MemoryReadError('Unexpected difficulty value; result cannot be verified.')
    if (game.pointer(game.base + GAME_LOGIC_RVA) != logic
            or game.pointer(game.base + CAMPAIGN_GLOBAL_RVA) != manager
            or game.pointer(game.base + SCRIPT_ENGINE_RVA) != scripts
            or game.read(manager + 8, 20) != before
            or any(game.read(logic + 0x51, 2)) or any(game.read(logic + 0x64, 1))
            or struct.unpack('<i', game.read(scripts + SCRIPT_DIFFICULTY_OFFSET, 4))[0] != active):
        raise MemoryReadError('Mission changed during the check. Try again after loading finishes.')
    return mission['name'].removesuffix(' - Victory'), campaign, active


def check_once():
    game = None
    try:
        game = GameMemory.find()
        if game is None:
            print('Game is not running. Start Steam Zero Hour and load a mission, then check again.')
            return 1
        mission, campaign, active = inspect_difficulty(game)
        print(f'\nMission: {mission}')
        print(f'Campaign difficulty: {DIFFICULTY_NAMES[campaign]} ({campaign})')
        print(f'Active mission scripts: {DIFFICULTY_NAMES[active]} ({active})')
        if campaign != active:
            print('MISMATCH: the two game settings disagree; send this output for investigation.')
            return 1
        print(f'CONFIRMED: this loaded mission is running on {DIFFICULTY_NAMES[active].upper()}.')
        return 0
    except OSError as error:
        print(str(error))
        return 1
    finally:
        if game is not None:
            game.close()


def main():
    parser = argparse.ArgumentParser(description='Read-only Steam Zero Hour difficulty checker')
    parser.add_argument('--once', action='store_true', help='Print one result and exit')
    args = parser.parse_args()
    print('Zero Hour - Mission Difficulty Checker\nRead-only; no server connection or game changes.\n')
    while True:
        result = check_once()
        if args.once:
            return result
        try:
            if input('\nLoad another save, then press Enter to check again (Q to quit): ').strip().lower() == 'q':
                return 0
        except (EOFError, KeyboardInterrupt):
            return 0
