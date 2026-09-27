"""Build an optional, clean mission-start pack without touching player saves."""
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from zh.mission_saves import all_saves, MissionSave

PACK_NAME = 'ZeroHour-Mission-Start-Saves-0.1.0'
README = '''# Zero Hour — Archipelago mission-start save pack 0.1.0

Optional pack for the stock Steam version of Zero Hour. 240 saves:
15 story missions and 65 Generals Challenge battles, each on Easy, Medium and Hard.

These are native MISSION saves, not point-in-time saves or Quick Reset checkpoints.
Loading one requests a NEW GAME for that map, campaign, mission and difficulty.
The map initializes normally, including its scripted opening scenes. Standalone
campaign-selection movies outside the map are not included in a mission save.

## Install and use

1. Close Zero Hour before copying saves. Keep the Archipelago client closed while copying.
2. Open your Documents/Command and Conquer Generals Zero Hour Data/Save folder.
   Create the Save folder if it does not exist. Documents may be redirected to OneDrive.
3. Open Easy/Save, Medium/Save or Hard/Save in this pack. Copy the desired .sav files
   directly into the game's Save folder. You may install one difficulty or all three.
   Do not copy the difficulty directories themselves: the game does not scan subfolders.
4. Names start with "Archipelago -". Preserve any existing files with the same names
   instead of overwriting them. None of the game's numbered or AP-QuickReset saves
   are used by this pack.
5. Start the client and game. Choose LOAD and select a named entry.
   To uninstall, remove only the files listed in manifest.csv that you installed.

Examples (the filename and in-game description both use these names):
  Archipelago - Easy - USA 1
  Archipelago - Easy - Infantry 1 - Vs. Air
  Archipelago - Hard - GLA 5

Air = Air Force; Nuclear = Nuke; Leang = the final Boss General.
Mission numbers follow the selected general's real campaign order, not opponent order.

## Archipelago behavior

These files contain no AP items, modified builder menus, timers, completed checks,
saved army, or saved player cash. The stock map creates the mission. Challenge
setup uses the native $10,000 lobby default before the map's own opening scripts.
Mission-set locks still apply: loading GLA 5 requires GLA Campaign Unlock.
Loading/skipping a mission does not award its check or its set-completion bonus.
The client must remain connected through loading for starting cash and other effects.

General promotion experience normally carries between missions. For independent
starts this pack uses these observed native mission-start baselines:
  USA:   0, 0, 800, 1500, 5000
  China: 0, 1500, 1500, 2500, 5000
  GLA:   0, 800, 800, 0, 0
  Challenges: 0 for battle 1, 5000 for later battles.
Actual carried experience can depend on prior play; these are fixed pack baselines.
The maps still apply their own rank limits and scripted initialization.

## Validation status

Generated from the published native save schema and stock Steam mission tables.
The encoder round-trips native mission-start examples byte-for-byte. Every generated
file is checked for type, campaign/map, difficulty, description, rank and (for
challenges) local general template. The user confirmed mission loading and
difficulty verification work as intended. Automated coverage includes all 240
files; this does not mean every mission has been played to victory.
This pack targets stock Steam player-template order;
overhaul mods that reorder factions are not supported.

Source reference:
https://github.com/electronicarts/CnC_Generals_Zero_Hour/blob/main/GeneralsMD/Code/GameEngine/Source/Common/System/SaveGame/GameState.cpp
'''


def main():
    output = ROOT / 'dist' / PACK_NAME
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime(2026, 9, 19, 12, 0, 0)
    records = []
    paths = []
    for difficulty, save in all_saves(timestamp):
        relative = Path(difficulty) / 'Save' / (save.description + '.sav')
        path = output / relative
        data = save.encode()
        assert MissionSave.decode(data) == save
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != data:
            raise RuntimeError(f'Refusing to replace a changed pack file: {path}')
        path.write_bytes(data)
        paths.append(relative)
        records.append(dict(file=relative.as_posix(), title=save.description,
            difficulty=difficulty, campaign=save.campaign, mission=save.mission,
            map=save.map_name, player_template=save.player_template,
            rank_points=save.rank_points, save_type='MISSION',
            sha256=hashlib.sha256(data).hexdigest()))
    if len(records) != 240 or len({r['title'] for r in records}) != 240:
        raise RuntimeError('Incomplete or duplicate mission-start pack')
    (output / 'README.txt').write_text(README, encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    table = io.StringIO(newline='')
    writer = csv.DictWriter(table, fieldnames=list(records[0]))
    writer.writeheader(); writer.writerows(records)
    (output / 'manifest.csv').write_text(table.getvalue(), encoding='utf-8-sig')
    # Explicit entries prevent accidental inclusion of any other files in dist.
    archive_path = output.parent / (PACK_NAME + '.zip')
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for relative in [*paths, Path('README.txt'), Path('manifest.json'), Path('manifest.csv')]:
            archive.write(output / relative, PACK_NAME + '/' + relative.as_posix())
    print(f'Built {len(records)} mission-start saves: {output}')
    return archive_path


if __name__ == '__main__':
    main()
