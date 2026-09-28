# Zero Hour Archipelago

**Launcher 0.8.2 — Steam preview** · World **0.20.0** · Archipelago **0.6.7** · Windows

Play the USA, China and GLA campaigns and Generals Challenges as part of an
Archipelago multiworld. Victories award checks; items unlock mission sets,
builders and permanent abilities.

**Supported: stock English Steam Command & Conquer: Generals - Zero Hour.**
Steam with GenPatcher v2.14 (Fixes Applied) and GenTool v8.9 installed through
GenPatcher are user-tested as working. GenLauncher, EA App, Origin and The First
Decade remain untested; GeneralsOnline is unsupported.
See [compatibility](docs/COMPATIBILITY.md) for the version-specific reports.

## Install and play

1. Download `ZeroHour-Archipelago-0.8.2-Steam.zip` from
   [GitHub Releases](https://github.com/ItsMrNew/ZeroHour-Archipelago/releases).
   Extract the whole ZIP into its own folder.
2. Install `generals_zh.apworld` in Archipelago's `custom_worlds` and restart
   Archipelago. The bundled client EXE does not need a separate Python install.
3. Open **Zero Hour Options.html**, choose settings and download your YAML.
   Expected check totals and item capacity update live. `ZeroHour.yaml` is an example.
4. Generate locally with Archipelago, host the seed and note the room address and
   exact player slot name.
5. Launch stock Zero Hour through Steam. Run **ZeroHourClient.exe**, enter the room
   and slot, and click **Connect**. Keep it open during play. If the game is
   elevated, run the client as administrator too.
6. On first connection, the client may install the separate Patriot definition.
   Restart Zero Hour when prompted before using Patriot Airdrop. Stock executable
   and INI files are not overwritten.

The default server `archipelago.gg:5000` is a placeholder; enter your hosted room.
Default slot: `ZeroHour`. Fields and Light/Dark theme are remembered. Blank fields
revert to defaults on the next launch.

This integration is for **single-player campaigns and Generals Challenges**, not
Zero Hour online matches. Archipelago connects those checks to other games.

## Features

- Three story campaigns and up to nine Generals Challenge campaigns.
- Mission-set unlocks, starting sets and optional exclusion of USA 3 / GLA 4.
- **1–10 checks per mission** (default 1), **0–10 per completed set** (default 5),
  and selectable victory goals.
- Twelve cross-faction builder unlocks, including specialist Generals.
- Four permanent abilities:

  | Ability | Effect | Normal cooldown |
  | --- | --- | --- |
  | Reveal Minimap | Reveals the map for 15 seconds | 3 minutes |
  | Carpet Bomb | Air Force bombing strike at the selected area | 4 minutes |
  | Patriot Airdrop | Three self-powered Patriots, standard health/weapons | 5 minutes |
  | Emergency Repair | Level 3: up to 300 HP per friendly vehicle, radius 100 | 4 minutes |

- Optional Progressive Generals Powers: each Progressive Generals Point adds one
  point to every mission's budget. Purchases are per mission; rank follows received
  points, with stock restrictions retained. Default count 18; range 0–28.
- Progressive Starting Cash (0–10 copies), automatic Supply Drops/Reinforcements,
  weighted traps and filler.
- Optional DeathLink: Full Restart or post-intro Quick Reset. Optional grace counts
  player-controlled game time, excluding cutscenes and pauses.
- Always-on Progress tracker, coloured transfer logs and notifications.
- Live notification filters/duration and DeathLink overrides without a new seed.

Progress, DeathLink and Notifications work at the main menu and while paused.
Builders and Abilities require mission control. Permanent cooldowns carry between
missions/resets; the YAML cooldown multiplier applies to all four abilities.

Traps are off by default. When enabled, the default split is 50% traps / 50% weighted
filler after fixed unlocks. Each trap weight defaults to 50; Supply Drop and
Reinforcements to 50; Mission Report to 0. These three non-trap items use filler
classification/colour.

## Updating

Close the older client and restart Zero Hour. Preserve
`%LOCALAPPDATA%\ZeroHourArchipelago`, which holds preferences and seed/slot progress.

Public **0.8.0** follows internal **0.21.1**; it is a naming change, not a rollback.
World **0.20.0**, protocol **17** and item/location IDs stay unchanged, avoiding a
world-version downgrade. Existing compatible rooms need no new seed. New seed
options/items require generation with their corresponding world.

## Package

The player ZIP includes the client, optional Start Client shortcut, AP world,
options creator/example YAML, optional mission-start saves, read-only Diagnostics,
compatibility guide and dependency licenses. Saves do not bypass mission locks
or grant victory checks. No test seeds, private YAMLs, credentials or game executables
are included.

## Support

Read [compatibility and troubleshooting](docs/COMPATIBILITY.md), then
[report an issue](https://github.com/ItsMrNew/ZeroHour-Archipelago/issues) with
client version, storefront, tools/mods, mission and diagnostic output. Do not share
passwords, settings files, private room data or game executables.

A changed SHA alone does not reject an update; code/layout changes can still
require an adapter update. Passing an offline check does not certify injected
tools or modified assets. The latest permanent Emergency Repair path has automated
coverage; live healing confirmation remains outstanding for this preview.

## Source workspace

See [development/builds](docs/DEVELOPMENT.md), [change history](CHANGELOG.md) and
[release notes](docs/releases/0.8.2.md).

Unofficial community integration; not an EA, Valve or Archipelago release.
