# Development and release builds

Use Windows, Python 3.12 with Tk, and Node.js. The player EXE needs neither a
separate Python installation nor Node.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q -s -p no:faulthandler
node tests/test_options_creator.cjs
.venv/Scripts/python.exe tools/release.py
```

Tk tests require `-s`; native callback tests use Unicorn. Game-dependent tests
skip without local assets. Set `ZERO_HOUR_TEST_EXE` to Steam or EA App Game.dat and
`ZERO_HOUR_TEST_DIR` to its directory for installed-binary/asset tests.

For generation/handshake validation using an Archipelago 0.6.7 source checkout:

```powershell
.venv/Scripts/python.exe tools/build.py
.venv/Scripts/python.exe tools/verify_generals_points.py PATH_TO_ARCHIPELAGO_SOURCE
```

## Layout

- `zh/`: launcher, protocol, native adapters.
- `worlds/generals_zh/`: AP world; shared tables synchronized by `tools/build.py`.
- `players/ZeroHour.yaml`: single supported example.
- `assets/`: current transparent artwork and multi-resolution icon.
- `tests/`, `tools/`, `docs/`: tests, builders/diagnostics, documentation.
- `dist/`, `build/`, `.research/`, `.cleanup-archive/`: ignored generated/local
  material. Screenshots and `.codex-remote-attachments/` are also excluded.

Keep private seeds/YAMLs in ignored local folders, not `players/`.

## Versions and packages

`zh/version.py` defines the launcher release. The current client is 0.8.4, with
world 0.21.0 and protocol 18. The AP network version remains 0.6.7.

The builder produces a Windows player ZIP for Steam and EA App, allowlisted source ZIP, standalone world,
release notes and SHA256SUMS in an upload folder. Player packaging uses an empty
staging folder. `--archive-only` leaves an extracted client untouched. EXE file
properties and title show the public version.

## Packaged Archipelago Launcher distribution

The regular launcher adapter, artwork, builder and tests live in
`tools/launcher_bundle/`. Build it separately after the standalone Windows build:

```powershell
.venv/Scripts/python.exe tools/launcher_bundle/build.py
.venv/Scripts/python.exe -m pytest tools/launcher_bundle/test_launcher.py -q
.venv/Scripts/python.exe tools/launcher_bundle/smoke_packaged_launcher.py
```

The builder reads `dist/ZeroHour-Archipelago-0.8.4-Windows` and produces
`dist/ZeroHour-Archipelago-0.8.4-Launcher` and its ZIP. It preserves the Windows
build, refuses to overwrite an existing launcher package, and does not install
into the user's Archipelago directory. The launcher APWorld registers the client;
the standalone world remains independent. The smoke check uses a sandbox copy of
installed Archipelago 0.6.7 and opens/closes only its own test client windows.

The launcher stores its extracted client and user data under
`%LOCALAPPDATA%\ZeroHourArchipelagoLauncher`, separate from the standalone client.
The repository README is the canonical first-time installation guide; the launcher
builder includes it both beside the APWorld and inside its client/setup resources.

## Compatibility

Native instruction/layout anchors and live signatures guard writes. An SHA is
diagnostic evidence, never a bypass. Alternate installations require independent
layout verification and live mission/ability/save/reset tests. A filename, Steam
folder or offline scan cannot certify a replacement engine or injected DLL.

## Publishing

Target: https://github.com/ItsMrNew/ZeroHour-Archipelago

1. Review source/validation and exclude credentials, private seeds and game files.
2. Select a project source license before describing it as open source. No project
   license has been chosen; dependency licenses are separate.
3. Commit reviewed source using the repository's existing main history.
4. After the user reviews the public instructions and authorizes publication,
   prepare the release for `Zero Hour Archipelago 0.8.4 - Steam and EA App`.
   Include the Launcher and standalone Windows builds as separate downloads.
5. Upload the prepared ZIPs, world and SHA256SUMS, then verify downloaded hashes.

The builder does not publish, tag or upload. CI runs tests only.

For a release containing both distributions, after final documentation review run
`.venv/Scripts/python.exe tools/launcher_bundle/prepare_uploads.py`. This stages
the two existing ZIPs, packaged-client APWorld, current allowlisted source ZIP,
README, options creator, example YAML and optional saves in
`dist/GitHub-v0.8.4-Public`, with a SHA256SUMS file. Publish that directory's
downloads using `docs/releases/0.8.4.md` for the release description. This does not
rebuild or alter the standalone Windows package.

Before declaring stable: confirm story and Challenge missions, all four abilities
(including healing a damaged vehicle), save/reload, DeathLink and reconnect.


## Timed build boost adapter

`zh/boosts.py` uses a private simulation-time mailbox, separate from saved game
objects. Production increments the current unit entry's frames-under-construction
by one before the normal update; the existing shutdown hook takes precedence.
Construction wraps the dozer action state's native update, temporarily halves
only the local player's building build-time handicap and restores its exact bits
before returning. It leaves native builder, health and completion logic intact.
GLA workers use the same DozerPrimaryStateMachine.

Source references (EA's released GeneralsMD engine):

- [ProductionUpdate.cpp](https://github.com/electronicarts/CnC_Generals_Zero_Hour/blob/main/GeneralsMD/Code/GameEngine/Source/GameLogic/Object/Update/ProductionUpdate.cpp)
- [DozerAIUpdate.cpp](https://github.com/electronicarts/CnC_Generals_Zero_Hour/blob/main/GeneralsMD/Code/GameEngine/Source/GameLogic/Object/Update/AIUpdate/DozerAIUpdate.cpp)
- [WorkerAIUpdate.cpp](https://github.com/electronicarts/CnC_Generals_Zero_Hour/blob/main/GeneralsMD/Code/GameEngine/Source/GameLogic/Object/Update/AIUpdate/WorkerAIUpdate.cpp)

New layout anchors verify the action-state constructor/table/update and build-time
handicap access. All 331 anchors resolve on both installed Steam and EA App builds.
The published boost code stays allocated until game exit; disconnect clears the
timers and restores native vtable entries. Tests execute the generated machine
code in Unicorn and check native calling conventions, ownership, expiry, stacking,
cutscenes, resets, shutdown priority and exact handicap restoration. They do not
replace live tests of USA/China dozers and GLA workers in missions.
