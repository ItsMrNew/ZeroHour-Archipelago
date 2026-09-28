# GeneralsOnline compatibility investigation

Date: 2026-09-27. Client: 0.8.1. Result: the installed GeneralsOnline build is
not compatible with the current native adapter. No working GeneralsOnline build
of the Archipelago client was produced by this investigation.

## Installed files inspected

All three files were in the same Steam game directory. Only their files and
configuration were read; no executable was launched, patched or attached to.

| File | Finding |
| --- | --- |
| `Game.dat` | Current adapter resolves all 327 required native anchors. |
| `GeneralsOnlineZH.exe` | Launcher, not the game engine. Version resources identify `GeneralsOnlineLauncher` / `Launcher.dll`. |
| `GeneralsOnlineZH_60.exe` | Different game engine; current adapter fails at its first required anchor (`0x1e00`, no matches). |

SHA-256 values for reproducing the inspection (not an allowlist):

```text
Game.dat
f37a4929f8d697104e99c2bcf46f8d833122c943afcd87fd077df641d344495b
GeneralsOnlineZH.exe
cdce2df2e9c4d278b268bb5822944796c93e616b5cad7989a149760b5acae5f1
GeneralsOnlineZH_60.exe
ff21df13c5cb0f524e4d56585c1867467efbcff44a94ed2e1b2f30eef2aaca8b
```

The engine's PE sections include `.themida` and `.boot`, consistent with binary
protection. Its on-disk image is not usable with the existing Steam instruction
signatures. This inspection does not establish the runtime addresses or object
layouts, nor show whether anti-cheat would block the client.

The installed `EasyAntiCheat/Settings.json` identifies `GeneralsOnlineZH_60.exe`
as its game executable. The official [April 2026 update notes](https://www.playgenerals.online/patchnotes/042826)
also confirm Easy Anti-Cheat activation. No anti-cheat setting was changed.

## Source inspection

The official [launcher source](https://github.com/GeneralsOnlineDevelopmentTeam/Launcher/blob/4d7cda7ce791d1256446d5b265945db427d2962b/Launcher/Pages/LauncherPage.xaml.cs)
selects either the game engine or `EAC_LaunchGeneralsOnline.exe`, depending on the
selected configuration. Adding the launcher filename to process detection would
attach to the wrong program.

The [game source](https://github.com/GeneralsOnlineDevelopmentTeam/GameClient/tree/cb290c8af1dc0411192638766912f6ed1d9e2470)
was inspected at commit `cb290c8af1dc0411192638766912f6ed1d9e2470`. This source
revision is not proven to match the installed protected binary.

Its `PluginInterfaces.h` exposes anti-cheat authentication, network transport,
logging and session callbacks. The inspected interface does not expose the
campaign-completion events, player state or game commands required by Archipelago.
CampaignManager and Player APIs exist in engine source, but they are not an
external Archipelago API.

## Work required for support

A separate engine integration is required. The preferred approach is a
campaign-only bridge in the game source, agreed with the GeneralsOnline project:

1. Export campaign/challenge identity, local player, victory/failure, pause and
   cinematic state through a versioned local interface.
2. Implement item effects, mission locks, points, DeathLink and menu operations
   on the game thread using the engine's own APIs.
3. Restrict the bridge to single-player campaign/Generals Challenge sessions and
   establish the supported anti-cheat configuration with the project.
4. Revalidate cooldown timing, object lifetimes, saves and every existing feature
   against the new engine before claiming support.

Simply accepting the EXE name or its SHA would leave the native addresses,
structure offsets and calling conventions unverified. The current process
detection and Steam validation therefore remain unchanged.

The existing Steam `Game.dat` remains the available Archipelago route in this
installation. This investigation made no changes to the installed game.
