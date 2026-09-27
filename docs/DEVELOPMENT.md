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
skip without local assets. Set `ZERO_HOUR_TEST_EXE` to Steam Game.dat and
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

`zh/version.py` defines the launcher release. Public 0.8.0 follows internal 0.21.1.
World 0.20.0 and protocol 17 stay unchanged. The AP network version remains 0.6.7.

The builder produces a Steam player ZIP, allowlisted source ZIP, standalone world,
release notes and SHA256SUMS in an upload folder. Player packaging uses an empty
staging folder. `--archive-only` leaves an extracted client untouched. EXE file
properties and title show the public version.

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
4. Tag `v0.8.0`; create a GitHub prerelease titled
   `Zero Hour Archipelago 0.8.0 - Steam preview`, using `docs/releases/0.8.0.md`.
5. Upload the prepared ZIPs, world and SHA256SUMS, then verify downloaded hashes.

The builder does not publish, tag or upload. CI runs tests only.

Before declaring stable: confirm story and Challenge missions, all four abilities
(including healing a damaged vehicle), save/reload, DeathLink and reconnect.
