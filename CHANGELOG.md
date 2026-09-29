# Changelog

## 0.8.4 - Timed helpful filler

- Promoted the packaged Archipelago Launcher client to the regular **Zero Hour
  Client** entry. Distributed as `ZeroHour-Archipelago-0.8.4-Launcher`, with the
  compact launcher icon and a dedicated `ZeroHourArchipelagoLauncher` data folder. The standalone
  `ZeroHour-Archipelago-0.8.4-Windows` build remains separate and unchanged.
- Fixed a follow-up minimap regression that caused the menu to report "Power hook
  data write failed verification". Radar callbacks are exclusive to gameplay
  effects; menu and DeathLink hooks retain their own allocations and cleanup.
- Fixed Power Outage leaving the minimap usable when campaign scripts force radar
  on (reported in China 1). Minimap drawing and clicks are blocked for the trap's
  duration, without changing mission radar settings or radar-provider counts.
- Added Production Surge and Construction Boost: 2x speed for 120 seconds of
  player control per item. Duplicate copies extend duration, not speed.
- Added both filler weights to the world, YAML creator, live pool preview and
  example YAML (0-100, default 50). Both use the light-blue filler colour.
- Boosts wait for mission control, freeze through cutscenes/pauses, and clear on
  mission reset/save load/client close. They do not affect enemies or research.
- Production Shutdown takes priority over Production Surge. Construction still
  requires its builder and follows normal health/power/completion behaviour.
- World 0.21.0 / protocol 18; older rooms remain supported. New seeds need the
  updated world to include boosts. Existing item and check IDs remain stable.

## 0.8.3 - Steam and EA App preview

- Access-denied messages appear red in both launcher themes.
- Players launch the EXE directly; diagnostic shortcuts use their console EXE.
- Recognizes stock English EA App Zero Hour as a compatible, supported installation.
- Updates launcher, diagnostics, setup and issue templates for both storefronts.
- Uses one Windows package for Steam and EA App. Existing native verification,
  world 0.20.0, protocol 17 and seed compatibility remain unchanged.

## 0.8.2 - Steam preview

- Archipelago-only source tree, tests and release packages.
- Retains the red mission-lock log messages and compatibility reports from 0.8.1.
- World 0.20.0 and protocol 17 remain compatible with existing seeds.

## 0.8.1 - Steam preview

- Mission-lock notices and the return-to-menu confirmation appear red in launcher
  logs, with readable shades for Light and Dark themes.
- Compatibility notes record Steam working with GenPatcher v2.14 (Fixes Applied)
  and GenTool v8.9 installed through GenPatcher, as reported by the user.
- GenLauncher remains untested; GeneralsOnlineZH.exe remains unsupported.
- World 0.20.0, protocol 17 and existing seed compatibility are unchanged.

## 0.8.0 - Steam preview

Public naming follows internal 0.21.1. World 0.20.0, protocol 17 and all IDs stay
unchanged.

- Explicit stock English Steam support scope and compatibility guide.
- Read-only executable report with SHA-256 and native-layout result.
- Public version in launcher title and executable properties.
- Clean packages, source archive, checksums, current setup and issue templates.
- Obsolete local launcher builds archived; existing gameplay features retained.

## Internal 0.21.0-0.21.1 / world 0.20.0

Added permanent Emergency Repair Level 3 (300 HP, radius 100, four-minute cooldown),
pool/starting options and backward room compatibility. Menu description now shows
only the cooldown.

## Earlier internal development

Mission progression/checks/goals, specialist builders, permanent abilities,
progressive points/cash, weighted traps/filler, DeathLink, live preferences,
main-menu tracker/notifications, themed launcher, saved fields and coloured logs.
