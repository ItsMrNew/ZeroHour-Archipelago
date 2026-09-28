# Compatibility and troubleshooting — 0.8.1

| Configuration | Support status |
| --- | --- |
| Stock English Steam Zero Hour on Windows: campaigns / Generals Challenges | Supported target |
| Steam + GenPatcher v2.14 with Fixes Applied | User-tested: working |
| Steam + GenTool v8.9 installed through GenPatcher | User-tested: working |
| GenLauncher | Untested |
| Other tool versions, custom DLLs or mods | Untested; reproduce on stock Steam first |
| GeneralsOnline / replacement engine | Not supported in this release |
| EA App / Ultimate Collection | Not validated |
| Origin | Not validated |
| First Decade / retail | Not validated |
| Other languages, Wine/Proton, online matches | Outside release scope |

These boundaries do not mean every other installation necessarily fails.
Native checks do not prove purchase source, and storefront guesses never bypass
validation.

## Services and modifications

GeneralsOnline is a source-based fork using `GeneralsOnlineZH.exe`. Its FAQ says
it coexists with the standard game without replacing it. Use the standard Steam
game for this release. [GeneralsOnline](https://www.playgenerals.online/)

Inspection of the installed files confirms `GeneralsOnlineZH.exe` is the launcher
and `GeneralsOnlineZH_60.exe` is a different engine that fails the current native
layout checks. The installed Easy Anti-Cheat configuration targets that engine.
Its runtime interaction with the client has not been tested. Supporting it needs
a separate engine integration; see the [investigation](GENERALS_ONLINE_INVESTIGATION.md).

GenTool's own supported-game list does not establish compatibility with this
client's native hooks. On 2026-09-27, the user confirmed Steam works with
GenPatcher v2.14 (Fixes Applied) and GenTool v8.9 installed through GenPatcher.
These are version-specific gameplay reports, not validation of every feature or
future tool release. GenPatcher and other tools may change configuration. We do
not assume they all modify the EXE.
[GenTool](https://www.gentool.net/) · [GenPatcher](https://www.gentool.net/genpatcher/)

DLLs can change a running game without changing Game.dat's hash. Different
storefront builds can have different layouts despite similar displayed versions.

## Read-only report

Run **Diagnostics/Check Compatibility.cmd** and enter the full Game.dat path
without quotes, or:

```powershell
./Diagnostics/ZeroHourClientConsole.exe --check-executable "D:/Games/Zero Hour/Game.dat"
```

No process attachment, game writes or server connection occur. The report contains
client version, filename, size, SHA-256 and layout result, not your full path,
credentials or seed data. Share it with storefront, language and tool/mod versions.

A pass checks the on-disk file only, not injected DLLs, changed assets or live
gameplay. Normal attachment and feature-specific checks still apply.

## Troubleshooting

- **Waiting:** start standard Zero Hour through Steam, not an alternative engine.
- **Layout rejection:** keep validation enabled; share the report/error. Engine
  changes require an adapter update, not an accepted-SHA edit.
- **Access denied:** run the client as administrator if the game is elevated.
- **First Patriot cast fails:** restart after installation of
  `Data/INI/Object/ZZArchipelagoPatriot.ini`; keep it for saves with those Patriots.
- **Slot/connection error:** use the actual room address and exact YAML slot name.
- **New settings ignored:** seed options need a new generated seed; presentation
  changes do not.
- **Upgrade:** close the old client and restart the game; preserve AP local progress.

Compare mods with a separate clean setup where possible; retain backups.
Steam verification may restore stock files without removing extra DLL/mod files.
The client never uninstalls these tools automatically.

Automated tests cover native callbacks, targeting, cooldowns, saves, protocol,
options and launcher behaviour. Executable-backed checks use the local Steam
build. This is not live coverage of every mission/storefront/mod. Permanent
Emergency Repair still needs live healing confirmation.
